"""年度半導體廠級排放離群模型；不使用虛構產量，不與舊月度 API 混用。"""
import argparse
import csv
import json
import math
import hashlib
from pathlib import Path
from datetime import datetime, timezone
import sklearn
from sklearn.ensemble import IsolationForest

CODES = {'2611': '積體電路製造業', '2612': '分離式元件製造業', '2613': '半導體封裝及測試業'}

def features(row):
    direct, indirect = float(row['tot1_value']), float(row['tot2_value'])
    if not all(math.isfinite(x) and x >= 0 for x in (direct, indirect)):
        raise ValueError('直接與間接排放必須為非負有限數字')
    total = direct + indirect
    return [math.log1p(direct), math.log1p(indirect), direct / total if total else 0.0]

def read(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))

def year(row):
    value = int(row['app_year'])
    return value + 1911 if value < 1911 else value

def eligible(row, industry):
    return (row['ccksicco1'] == industry and row['sicname1'] == CODES[industry]
            and row['check_yn'] == '是')

def fit(samples, contamination):
    model = IsolationForest(n_estimators=200, max_samples=min(256, len(samples)),
                            contamination=contamination, random_state=42, n_jobs=1)
    model.fit([features(row) for row in samples])
    return model

def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='action', required=True)
    train = sub.add_parser('train')
    train.add_argument('--input', required=True)
    train.add_argument('--industry', choices=list(CODES), required=True)
    train.add_argument('--year', type=int, required=True, help='西元年度，例如 2023')
    train.add_argument('--model', required=True)
    train.add_argument('--contamination', type=float, default=.05)
    score = sub.add_parser('score')
    score.add_argument('--input', required=True)
    score.add_argument('--model', required=True)
    score.add_argument('--year', type=int, required=True)
    score.add_argument('--output', required=True)
    args = parser.parse_args()
    if args.action == 'train':
        if not 0 < args.contamination <= .5:
            parser.error('contamination 必須介於 0（不含）到 0.5')
        rows = read(args.input)
        samples = [r for r in rows if eligible(r, args.industry) and year(r) == args.year]
        if len(samples) < 32:
            parser.error('此行業此年度少於 32 筆，不建立模型；不可複製樣本補數量')
        if len({r['controlno'] for r in samples}) != len(samples):
            parser.error('同年度重複廠別，請先清理')
        fit(samples, args.contamination)
        document = {'industry': args.industry, 'train_year': args.year,
                    'contamination': args.contamination, 'samples': samples,
                    'sklearn': sklearn.__version__,
                    'created_at_utc': datetime.now(timezone.utc).isoformat(),
                    'source_csv_sha256': hashlib.sha256(Path(args.input).read_bytes()).hexdigest(),
                    'feature_version': 'annual-direct-indirect-share-v1'}
        with Path(args.model).open('x', encoding='utf-8') as stream:
            json.dump(document, stream, ensure_ascii=False, indent=2)
        print('模型參考資料已保存：', args.model, '樣本數：', len(samples))
        print('這是離群模型，並未驗證資料真偽或分類準確率。')
    else:
        document = json.loads(Path(args.model).read_text(encoding='utf-8'))
        if document['sklearn'] != sklearn.__version__:
            parser.error('scikit-learn 版本不同，請使用原版本')
        if args.year <= document['train_year']:
            parser.error('此命令只評估訓練年度之後的年度，避免回填式評估')
        samples = [r for r in read(args.input)
                   if eligible(r, document['industry']) and year(r) == args.year]
        if not samples:
            parser.error('指定行業與年度沒有可評分紀錄')
        model = fit(document['samples'], document['contamination'])
        scores = -model.score_samples([features(r) for r in samples])
        flags = model.predict([features(r) for r in samples])
        fields = list(samples[0]) + ['outlier_score', 'review_required', 'training_year']
        with Path(args.output).open('x', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for row, score_value, flag in zip(samples, scores, flags):
                # 匯出防止公司名稱被試算表誤認為公式。
                row = dict(row)
                for key, value in row.items():
                    if value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t','\r','\n')):
                        row[key] = "'" + value
                writer.writerow({**row, 'outlier_score': float(score_value),
                                 'review_required': bool(flag == -1),
                                 'training_year': document['train_year']})
        print('已評分：', len(samples), '筆，輸出：', args.output)
        print('缺少人工異常標籤，不能報告準確率、召回率或證明造假。')

if __name__ == '__main__':
    main()
