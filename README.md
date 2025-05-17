# 🎥 LiveLeaper

**LiveLeaper** は、Pythonで開発されたシンプルかつ高機能な **YouTube動画ダウンローダー** です。使いやすさと高い柔軟性を兼ね備え、お気に入りの動画を簡単に保存して、オフラインでも楽しむことができます。

---

## 📌 概要

LiveLeaperは、直感的なGUIと強力なダウンロードエンジンを搭載したYouTubeダウンロードアプリケーションです。動画や音声を自由な形式で保存でき、今後はプレイリストや字幕の対応なども予定しています。

---

## ✨ 主な特徴

- 🖱️ **シンプルでわかりやすい操作性**  
  初心者の方でもすぐに使い始められる、直感的なインターフェースを採用しています。

- ⚡ **高速なダウンロード処理**  
  `yt-dlp`を活用し、高速かつ高品質な動画・音声のダウンロードが可能です。

- 🎵 **複数フォーマットへの対応**  
  MP4、MP3 などの形式に対応。音声だけの保存も可能です。

- 📃 **字幕の取得（※実装予定）**  
  字幕付き動画では、字幕ファイルの保存にも対応予定です。

- 📂 **プレイリストの一括取得（※実装予定）**  
  YouTubeのプレイリスト全体をワンクリックで保存できるよう対応予定です。

---

## 💻 動作環境

- Python 3.8以上を推奨（3.x系）

---

## 📦 依存ライブラリ

以下のライブラリが必要です（すべて `requirements.txt` に記載済みです）：

- [`yt-dlp`](https://github.com/yt-dlp/yt-dlp)：動画・音声のダウンロード処理
- [`pytube`](https://github.com/pytube/pytube)：補助的にYouTubeの解析処理に使用
- [`PyQt5`](https://pypi.org/project/PyQt5/)：GUI構築用
- [`PyQtWebEngine`](https://pypi.org/project/PyQtWebEngine/)：GUI内での動画プレビューなどに使用
- [`ffmpeg`](https://ffmpeg.org/)（※別途インストール）：動画変換および音声抽出処理

---

## 📥 インストール方法

### 🔹 Windowsをご利用の方

1. [GitHubリリースページ](https://github.com/yunfie-twitter/LiveLeaper/releases) から、最新版の実行ファイルをダウンロードしてください。

### 🔸 全OS共通（ソースコードから）

1. Python 3.x をインストールしておきます。  
2. 以下のコマンドで必要な依存ライブラリをインストールします：

    ```bash
    pip install -r requirements.txt
    ```

3. GitHubからLiveLeaperをクローンまたはZIPダウンロードします：

    ```bash
    git clone https://github.com/yunfie-twitter/LiveLeaper.git
    cd LiveLeaper
    ```

---

## ▶️ 使い方

1. ターミナルまたはエクスプローラーから、`liveleaper.py` を実行します：

    ```bash
    python liveleaper.py
    ```

2. アプリのGUIが立ち上がったら、YouTube動画のURLを入力してください。  
3. フォーマットや保存先を選択し、「ダウンロード」をクリックするだけで処理が開始されます。  
4. 処理が完了すると、指定されたフォルダにファイルが保存されます。

---

## ⚠️ 注意事項

- 本ソフトウェアはYouTubeの利用規約を尊重し、著作権を侵害しない範囲での利用を前提としています。
- 商用目的での利用や再配布については、Apache License 2.0ライセンスの条件を遵守してください。
- `yt-dlp`やYouTube側の仕様変更により、予告なく動作に影響が出る可能性があります。

---

## 📜 ライセンス

本プロジェクトは [Apache License 2.0](LICENSE) のもとで公開されています。自由な改変・配布が可能ですが、著作権表記の保持が必要です。

---

## 🤝 コントリビューションについて

バグの報告、改善提案、新機能の提案など、どんな形でも貢献を歓迎しています！  
GitHub上で Issue や Pull Request を通じてご連絡ください。

---

## 🌐 作者のホームページ

[ゆんふぃの小さな記録帳](https://notes.yunfie.org)

---

## 🗓️ 更新履歴

- **2025-05-11:** 初版リリース

    <style>
    body { font-family: sans-serif; line-height: 1.6; margin: 2em; background: #f8f9fa; }
    h1, h2 { color: #333; }
    .container { max-width: 800px; margin: auto; background: #fff; padding: 2em; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
    a { color: #007bff; text-decoration: none; }
    a:hover { text-decoration: underline; }
    code { background: #eee; padding: 2px 4px; border-radius: 4px; }
  </style>
