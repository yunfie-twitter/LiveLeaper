# LiveLeaper

**LiveLeaper** は、YouTube 動画を簡単にダウンロードできる Python 製ツールです。  
コマンドライン（CLI）版と、サブモジュールとして含まれる GUI 版の両方をサポートしています。

---

## ✅ 特徴

- 🎬 **YouTube対応** - 高品質動画のダウンロードに対応（`yt-dlp`を使用）
- 🖥️ **CLI & GUI両対応** - ターミナルが苦手な人でも使える
- ⚡ **高速かつ安定** - 公式APIではなく直接ストリーミングURLを解析
- 🪟 **マルチOS対応** - Windows / macOS / Linux 上で動作

---

## 🖥️ 動作環境

- Python 3.8 以上
- OS: Windows 10+ / macOS 10.14+ / Debian系 Linux (Ubuntuなど)

---

## 📦 インストール手順

```bash
# リポジトリをクローン（サブモジュールも含めて）
git clone --recurse-submodules https://github.com/yunfie-twitter/LiveLeaper.git
cd LiveLeaper

# 仮想環境を作成して有効化
python3 -m venv venv
source venv/bin/activate  # Windows の場合: venv\Scripts\activate

# 必要なパッケージをインストール
pip install -r requirements.txt

```

## 🎛 GUI版を使用する
```bash
cd LiveLeaper-GUI
pip install -r requirements.txt
python main.py
```

## ⚙️ CLI版の使い方
```bash
python main.py [URL1 URL2 ...] [オプション]
```

使用可能なオプション
オプション	説明
--audio	音声のみを抽出して保存（デフォルト設定ファイルに準拠）
--ext	出力ファイルの拡張子を指定（例：mp4, webm, mp3）
--output	保存先ディレクトリ（例：downloads）
--lang	言語ファイルを指定（例：en, ja）
--info	ダウンロードせず、動画情報のみを取得

## 🤝 貢献方法
Pull Request や Issue は大歓迎です！
```bash
# ブランチ作成
git checkout -b feature/your-feature

# コード編集・コミット
git commit -m "Add new feature"

# プッシュしてPRを作成
git push origin feature/your-feature
```

## [Sponsor this project By Ko-Fi](https://ko-fi.com/liveleaper).
