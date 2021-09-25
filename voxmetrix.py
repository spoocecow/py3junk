"""
funny little guy to count videochess vox usages
spoocecow 2021
"""
from bs4 import BeautifulSoup
import urllib.request
import re
from typing import List, Dict


debug = True


def get_html(url: str) -> BeautifulSoup:
   return BeautifulSoup(
      urllib.request.urlopen(url).read(),
      'html.parser'
   )

def get_log_listing() -> List[str]:
   url = 'https://rook.zone/voxlogs/'
   return [
      a.text for a in get_html(url).find_all('a') if '.txt' in a.text
   ]

def get_log(fn: str) -> str:
   url = 'https://rook.zone/voxlogs/' + fn
   return urllib.request.urlopen(url).read().decode('utf-8')


def get_vocab(include_warns=True, include_letters=True, include_morshu=False) -> List[str]:
   url = 'https://rook.zone/voxinfo.htm'
   vocab_boxes = [box.text for box in get_html(url).find_all('div', 'vocab')]
   vocab = vocab_boxes[0].split()
   if include_morshu:
      vocab += vocab_boxes[1].split()  # TODO should differentiate from normal vox where overlap?
   if include_warns:
      vocab += vocab_boxes[2].split()
   if include_letters:
      vocab += vocab_boxes[3].split()
   # notes are #4, not bothering with rn
   return vocab


def get_log_counts(raw_log: str, vocab: List[str]) -> Dict[str, int]:
   d = {w: 0 for w in vocab}
   # make these troublesome guys easier to isolate
   clean_log = raw_log.replace("'s", " 's ").replace("n't", " n't ")
   # future: record who the voxes came from for personal stats...!
   clean_log = re.sub(r'^From .*$', '', clean_log)
   # make the regex easier
   clean_log = re.sub(r"^", ' ', clean_log, re.MULTILINE)
   for w in vocab:
      d[w] = len(
         re.findall(rf'[\s+\-.,?!\d]{w}[\s+\-><.,?!]',  # can't use \W, else 's / n't double count for s/n/t
                    clean_log,
                    re.MULTILINE)
      )
   return d


def to_csv(counts: Dict[str, int]):
   s = "Word,Count\n"
   s += "\n".join(
         sorted([f"{w},{c}" for (w,c) in counts.items()])
   )
   return s + "\n"


def main():
   vocab = get_vocab()
   if debug:
      with open(r"C:\tmp\logsmash.txt") as f:
         logsmash = f.read()
   else:
      logfiles = get_log_listing()
      logsmash = ''
      for f in logfiles:
         print("Getteing", f)
         logsmash += get_log(f) + '\n'
   print("Counteing...")
   d = get_log_counts(logsmash, vocab)
   for i, (w,c) in enumerate(sorted(d.items(), key=lambda x:x[1], reverse=True)[:25]):
      print( f"{i}. {w}\t{c}" )
   csv = to_csv(d)
   if debug:
      with open(r"C:\tmp\voxcounts.csv", "w+") as f:
         f.write(csv)
      with open(r"C:\tmp\logsmash.txt", "wb+") as f:
         f.write(logsmash.encode('utf-8'))
   return d


if __name__ == "__main__":
   main()