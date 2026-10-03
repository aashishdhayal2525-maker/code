import sys; sys.path.insert(0, ".")
import itertools, numpy as np, pandas as pd
from dataclasses import replace
from research.calibrate import b60, score, compute, Params
from research.real_signals import WINDOW
rows=[]
for L,k in itertools.product((10,14,20,30,40),(5.5,6,6.5,7,8)):
    h,n,e=score(compute(b60,replace(Params(),st_atr_len=L,st_slow_mult=k,st_fast_mult=k-1)))
    rows.append((L,k,h,n,round(np.mean(np.abs(e)),2) if e else None, e))
print(pd.DataFrame(rows,columns=["atr","mult","hit","n","err","errs"]).to_string(index=False))
b=compute(b60,replace(Params(),st_atr_len=20,st_slow_mult=6,st_fast_mult=5))
w=b.loc[WINDOW[0]:WINDOW[1]]
print(w.loc[w.buy|w.sell|w.magic_buy|w.magic_sell,["close","buy","sell","magic_buy","magic_sell","cyan_dir","ema_dir","st_slow","cyan","ema"]].round(0).to_string())
