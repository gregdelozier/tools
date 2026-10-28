"""Deterministic crossword fallback for substantive course chapters.

Existing puzzles are preserved. Missing puzzles use bold definitions from the
chapter, with repeated prose words as a fallback. No network or model calls.
Delete generated-crossword.pdf to regenerate from the current source.
"""
from pathlib import Path
from collections import Counter
import hashlib
import json
import random
import re
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.utils import simpleSplit


def entries_from_text(text):
    body = text.split('## References')[0]
    body = re.sub(r'```.*?```', '', body, flags=re.S)
    paragraphs = [p.replace('\n', ' ') for p in body.split('\n\n')
                  if p.strip() and not p.lstrip().startswith(('#', '|', ':::','<!--'))]
    entries = []
    seen = set()
    for paragraph in paragraphs:
        for term in re.findall(r'\*\*([^*]+)\*\*', paragraph):
            answer = re.sub('[^A-Za-z]', '', term).upper()
            if not 3 <= len(answer) <= 24 or answer in seen or len(term.split()) > 3:
                continue
            # Use the sentence containing the defined term, not a whole paragraph.
            sentence = next((s for s in re.split(r'(?<=[.!?]) +', paragraph)
                             if '**' + term + '**' in s), '')
            clue = sentence.replace('**' + term + '**', '_____').replace('**','')
            clue = re.sub(r'\(\d+\)', '', clue).strip()
            clue = re.sub(r' +([.,;:!?])', r'\1', clue)
            if not 20 <= len(clue) <= 210:
                continue
            if answer in re.sub('[^A-Za-z]', '', clue).upper():
                continue
            entries.append((answer, clue)); seen.add(answer)
    if len(entries) < 8:
        plain = ' '.join(paragraphs)
        counts = Counter(re.findall(r'\b[a-zA-Z]{7,14}\b', plain.lower()))
        stop = {'because','another','something','different','without','through','between',
                'whether','example','examples','chapter','following','already','should','before'}
        for term in sorted(counts, key=lambda t: (-counts[t], t)):
            if term in stop or term.upper() in seen: continue
            for sentence in re.split(r'(?<=[.!?]) +', plain):
                if re.search(r'\b'+term+r'\b',sentence,re.I) and 35<=len(sentence)<=180:
                    clue=re.sub(r'\b'+term+r'\b','_____',sentence,flags=re.I).replace('**','')
                    entries.append((term.upper(),clue));seen.add(term.upper());break
            if len(entries)>=12:break
    return entries[:14]


def ensure_crossword(source):
    source = Path(source)
    # Only chapter manuscripts, never slides, notes, or arbitrary Markdown.
    if not source.parent.name.startswith('chapter-') or not source.name.startswith('chapter-'):
        return
    text = source.read_text()
    if len(text.split()) < 250:
        print('Crossword skipped: chapter is an outline')
        return
    destination = source.parent / 'exercises'
    existing = [p for p in destination.glob('*.pdf')
                if 'crossword' in p.name.lower() and not p.name.startswith('.private')
                and not set(re.split(r'[^a-z]+',p.stem.lower())) &
                {'key','keys','answer','answers','solution','solutions'}]
    if existing:
        print('Crossword retained: ' + str(sorted(existing)[0]))
        return
    clue_source = destination / "crossword-entries.json"
    entries = json.loads(clue_source.read_text()) if clue_source.exists() else entries_from_text(text)
    if len({entry[0] for entry in entries}) != len(entries):
        raise ValueError("Duplicate crossword answers")
    if len(entries) < 4:
        raise ValueError('Chapter needs at least four usable crossword definitions')
    destination.mkdir(exist_ok=True)
    title = re.search(r'^# (.+)', text, re.M).group(1)
    title = re.sub(r'^Chapter \d+: *', '', title)
    digest = hashlib.sha256((text + json.dumps(entries, sort_keys=True)).encode()).hexdigest()
    generate(entries, destination, title, int(digest[:16], 16))
    (destination / 'crossword-source.json').write_text(json.dumps(
        {'source_sha256': digest, 'generator_version': 1}, indent=2)+'\n')


def generate(ENTRIES, destination, title, seed_base):
    def construct(seed):
     rng=random.Random(seed); grid={}; directions={}; placed=[]
     words=ENTRIES.copy(); rng.shuffle(words); words.sort(key=lambda e:-len(e[0]))
     for word,clue in words:
      candidates=[]
      if not grid: candidates=[(0,0,0,0)]
      else:
       for (r,c),letter in list(grid.items()):
        for i,ch in enumerate(word):
         if ch!=letter: continue
         for d in (0,1):
          dr,dc=(0,1) if d==0 else (1,0)
          sr,sc=r-dr*i,c-dc*i
          if (sr-dr,sc-dc) in grid or (sr+dr*len(word),sc+dc*len(word)) in grid: continue
          cross=0; valid=True
          for j,ch2 in enumerate(word):
           pos=(sr+dr*j,sc+dc*j)
           if pos in grid:
            if grid[pos]!=ch2 or d in directions[pos]:valid=False;break
            cross+=1
           elif (pos[0]+dc,pos[1]+dr) in grid or (pos[0]-dc,pos[1]-dr) in grid:
            valid=False;break
          if valid and cross:
           rr=[p[0] for p in grid]+[sr,sr+dr*(len(word)-1)]
           cc=[p[1] for p in grid]+[sc,sc+dc*(len(word)-1)]
           h=max(rr)-min(rr)+1;w=max(cc)-min(cc)+1
           if max(h,w)<=29:
            candidates.append((h*w-cross*10+rng.random()*15,sr,sc,d))
      if not candidates:continue
      _,r,c,d=min(candidates); dr,dc=(0,1) if d==0 else (1,0)
      for i,ch in enumerate(word):
       pos=(r+dr*i,c+dc*i);grid[pos]=ch;directions.setdefault(pos,set()).add(d)
      placed.append(dict(answer=word,clue=clue,row=r,col=c,direction=d))
     return grid,placed

    best=None
    for seed in range(400):
     g,p=construct(seed + seed_base)
     h=max(r for r,c in g)-min(r for r,c in g)+1;w=max(c for r,c in g)-min(c for r,c in g)+1
     score=(len(p),-h*w)
     if best is None or score>best[0]:best=(score,g,p)
    _,grid,placed=best
    assert len(placed) >= min(8, len(ENTRIES)), "Too few connected entries"
    r0=min(r for r,c in grid);c0=min(c for r,c in grid)
    grid={(r-r0,c-c0):v for (r,c),v in grid.items()}
    for p in placed:p['row']-=r0;p['col']-=c0
    starts=sorted({(p['row'],p['col']) for p in placed})
    numbers={pos:i+1 for i,pos in enumerate(starts)}
    for p in placed:p['number']=numbers[p['row'],p['col']]
    # Verify every maximal horizontal/vertical sequence corresponds to an entry.
    actual=set()
    for r,c in grid:
     for d,(dr,dc) in enumerate(((0,1),(1,0))):
      if (r-dr,c-dc) in grid:continue
      word='';rr,cc=r,c
      while (rr,cc) in grid:word+=grid[rr,cc];rr+=dr;cc+=dc
      if len(word)>1:actual.add((r,c,d,word))
    assert actual=={(p['row'],p['col'],p['direction'],p['answer']) for p in placed}
    base=destination
    (base/'generated-crossword-data.json').write_text(json.dumps(placed,indent=2)+'\n')
    h=max(r for r,c in grid)+1;w=max(c for r,c in grid)+1
    cell=min(19,300/h,500/w);x0=(612-w*cell)/2;top=687
    for answer in (False,True):
     out=base/('generated-crossword-key.pdf' if answer else 'generated-crossword.pdf')
     pdf=canvas.Canvas(str(out),pagesize=(612,792), invariant=1)
     pdf.setTitle(title + ' - ' + ('Answer Key' if answer else 'Crossword'))
     pdf.setFillColor(black);pdf.setFont('Helvetica-Bold',16)
     pdf.drawString(42,750,title[:65])
     pdf.setFont('Helvetica',11);pdf.drawString(42,730,'Crossword' + (' - Answer key' if answer else ' - Chapter review'))
     pdf.setFont('Helvetica',9)
     pdf.drawString(42,710,'Use chapter concepts to solve the clues. Omit spaces and punctuation in the grid.')
     for r in range(h):
      for c in range(w):
       x=x0+c*cell;y=top-(r+1)*cell
       pdf.setFillColor(white if (r,c) in grid else HexColor('#343434'))
       pdf.setStrokeColor(black);pdf.setLineWidth(.45);pdf.rect(x,y,cell,cell,fill=1)
       if (r,c) not in grid:continue
       pdf.setFillColor(black)
       if (r,c) in numbers:
        pdf.setFont('Helvetica',5.5);pdf.drawString(x+1.3,y+cell-6,numbers[r,c].__str__())
       if answer:
        pdf.setFont('Helvetica-Bold',cell*.58);pdf.drawCentredString(x+cell/2,y+cell*.14,grid[r,c])
     clue_top=top-h*cell-23
     for d,clue_heading in ((0,'Across'),(1,'Down')):
      x=42+d*270;y=clue_top
      pdf.setFont('Helvetica-Bold',12);pdf.drawString(x,y,clue_heading);y-=17
      for p in sorted((p for p in placed if p['direction']==d),key=lambda p:p['number']):
       text=f"{p['number']}. {p['clue']}"
       if answer:text=f"{p['number']}. {p['answer']}"
       lines=simpleSplit(text,'Helvetica',9,250)
       pdf.setFont('Helvetica',9)
       for line in lines:pdf.drawString(x,y,line);y-=11
       y-=5
      assert y>35,('Clues overflow',y)
     pdf.setFont('Helvetica',8);pdf.drawString(42,23,'Chapter concept review');pdf.drawRightString(570,23,'Answer key' if answer else 'Student puzzle')
     pdf.showPage()
     pdf.save()
     print(f'{out}: {w} x {h}, {len(placed)} entries; grid and clue layout validated')
