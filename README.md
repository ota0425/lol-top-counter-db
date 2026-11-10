# LoL TOP対面対策DB

公開サイト：**https://ota0425.github.io/lol-top-counter-db/**

キショオタch「家族でイッキ見！バカでもわかる対策まとめ.top」の日本語自動字幕を基に、チャンピオン別の対策を検索するローカルWebアプリです。

- 対象動画：https://www.youtube.com/watch?v=gmuF58MD3ts
- 50チャンピオン、202件の対策要約を収録しています。
- 要約は各チャプター冒頭の対策解説を中心に整理しました。試合実況の全発言を対策として網羅したものではありません。
- 映像・音声とは未照合です。自動字幕の誤認識を含む可能性があります。元動画は2025年9月公開で、現行パッチへの適合は確認していません。

## 起動（Windows PowerShell）

このフォルダで次を実行します。

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

次回からは最後の1行だけで起動できます。ブラウザで `http://localhost:8501` を開きます。

PythonとStreamlitがすでに使える場合：

```bash
python -m streamlit run app.py
```

## 使い方

1. 「対策を検索」にチャンピオン名を入力します。部分一致、日本語・ひらがな・半角カナ・英語名に対応しています。例：`カミール`、`かみーる`、`Camille`。`カ・サンテ`、`ドクター・ムンド`等の別表記でも検索できます。
2. 検索結果には分類と対策内容を表示します。出典・字幕・確認状況は表示しません。
3. 収録済みの対策と動画で確認済みの手入力ノートを検索できます。
4. 「対策を登録・確認」で内容・分類・時刻を編集し、実際に動画で確かめたものを「確認済み」にします。出典時刻はそのチャンピオンのチャプター内で指定します。
5. 手入力の未確認ノートは検索に表示しません。確認済みへの変更後に表示されます。
6. 「字幕・チャプターを取り込む」でSRT/VTTやバックアップJSONを取り込めます。通常は収録済みのデータですぐ検索できるため、初期登録は不要です。

## データとバックアップ

- SQLite DBは `counters.sqlite3` です。停止した状態でコピーすれば字幕を含めてバックアップできます。
- 対策とチャプターは「対策を登録・確認」からJSONでエクスポート・復元できます。JSONには字幕は含めません。同じ内容の対策は重複追加せず、既存の確認状況やチャプター時刻を維持します。
- `data/counters.json`：時刻・分類・作成元を持つ対策要約。直接利用できるJSONです。
- `data/transcript.ja.json`：ローカル環境の任意の字幕ファイル。公開リポジトリには含めません。存在しなくても検索アプリは起動します。
- `data/source.json`：動画情報と概要欄由来のチャプター時刻。
- 初回起動時に同梱データを読み込みます。その後の編集・削除は再起動しても維持します。
- アプリの利用中に外部AI APIへの送信や字幕の再取得は行いません。

## 開発時の検証

```bash
python3 -m unittest discover -s tests -v
python3 -m streamlit run app.py
```

DB処理は `db.py`、画面は `app.py` です。追加のAPIキーや有料サービスは不要です。

## GitHub Pagesでの公開

公開版は `docs/index.html` です。対策の検索に対応し、出典・字幕・確認状況は表示しません。編集機能はローカルのStreamlitアプリで利用できます。

生成し直す場合：

```bash
python3 scripts/build_site.py
```

ローカルDBで編集した内容を反映する場合：

```bash
python3 scripts/build_site.py --database counters.sqlite3
```

更新した `docs/index.html` をGitHubへ反映すると、GitHub Pagesが再公開します。公開設定は `main` ブランチの `/docs` です。公開ページは自動字幕やSQLiteのDBファイルを配信しません。
