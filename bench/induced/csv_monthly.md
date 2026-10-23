---
recipe: csv_monthly
version: 0
verified: 未验证
models: []
server: <填>
---
# 配方草稿：csv_monthly

<!-- 由 2 份成功轨迹归纳。标「可能是试探」的步骤只在部分轨迹出现，先判断要不要留。参数里的 <占位> 要换成「来源说明」。补完「不要做 / 成功判据 / 失败时」后再体检、A/B。 -->

## 路线 A：<从轨迹归纳的做法>（候选）
**条件**：<填>
1. `list_dir(path=".")`
2. 执行：`ls -la sales/ && wc -l sales/sales_raw.csv && head -20 sales/sales_raw.csv`（可能是试探：只在部分轨迹出现）
3. 执行：`cd . && python -c "
import csv,collections,re
rows=list(csv.DictReader(open('sales/sales_raw.csv',newline='',encoding='utf-8-sig')))
print(len(rows), rows[0].keys())
print('regions:',collections.Counter(r['region'] for r in rows))
print('st`
4. 执行：`cd . && python -c "
import csv,collections,re
rows=list(csv.DictReader(open('sales/sales_raw.csv',newline='',encoding='utf-8-sig')))
amt=[]
for r in rows:
    a=r['amount']
    k=re.sub(r'[0-9]','9',a)
    amt.append(k)
print(collections.Co`
5. 执行：`cd . && python -c "
import csv,collections,re
rows=list(csv.DictReader(open('sales/sales_raw.csv',newline='',encoding='utf-8-sig')))
c=collections.Counter(r['order_id'] for r in rows)
dups={k:v for k,v in c.items() if v>1}
print('dup ids:',`
6. 执行：`cd . && python -c "
import csv,collections
rows=list(csv.DictReader(open('sales/sales_raw.csv',newline='',encoding='utf-8-sig')))
g=collections.defaultdict(list)
for r in rows: g[r['order_id']].append(tuple((v or '').strip() for v in r.valu`
7. `write_file(path="build_monthly.py", content=<值>)`（可能是试探：只在部分轨迹出现）
8. 执行：`cd . && python build_monthly.py && cat monthly.csv && python -c "
import csv
from decimal import Decimal
r=list(csv.DictReader(open('monthly.csv')))
print('rows',len(r),'months',len({x['month'] for x in r}),'regions',sorted({x['region'] for`
9. 执行：`cd . && python - <<'EOF'
import re
s=open('build_monthly.py',encoding='utf-8').read()
s=s.replace('''    if len(parts[2]) == 4:          # 年/月/日
        y, m, d = parts
    else:                            # 日/月/年
        d, m, y = parts'''`
10. 执行：`cd . && python - <<'EOF'
# independent re-implementation (different code path) for cross-check
import re
from collections import defaultdict
lines=[l.rstrip('\n') for l in open('sales/sales_raw.csv',encoding='utf-8-sig')][1:]
seen=set(); ag`（可能是试探：只在部分轨迹出现）
11. 执行：`cd . && file monthly.csv; head -3 monthly.csv | od -c | head -5; echo '---'; awk -F, 'NR>1{s+=$3} END{printf "%.2f\n", s}' monthly.csv; wc -l monthly.csv`（可能是试探：只在部分轨迹出现）
12. 执行：`cd . && python -c "
d=open('monthly.csv','rb').read().replace(b'\r\n',b'\n')
open('monthly.csv','wb').write(d)
" && od -c monthly.csv | head -3 && wc -l monthly.csv && rm -f build_monthly.py && ls`（可能是试探：只在部分轨迹出现）

**成功判据**：<填：做完时能核对的事实>
**失败时**：<填>

## 不要做
- <从失败的调用里总结：本次轨迹里失败过的调用见下方>

