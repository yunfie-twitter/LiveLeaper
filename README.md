# LiveLeaper - 動画・音声ダウンロード変換ツール

YouTubeやニコニコ動画などから動画や音声を簡単にダウンロード・変換できるPython製のGUIツールです。

---

## 特長

- **YouTube、ニコニコ動画対応のURL自動修正機能**
- **動画・音声のダウンロードと変換**（MP4, MP3, AACなど対応）
- **PyQt5ベースの使いやすいGUI**
- **バッチ処理と並列ダウンロード対応**
- **ハードウェアエンコード対応**（NVIDIA NVENC、Intel QSVなど）
- **初期設定ウィザードで簡単セットアップ**
- **詳細なログと進捗表示**
- **クロスプラットフォーム対応**（Windows, Linux, macOS）

---

## インストール

Python 3.8以上が必要です。依存ライブラリは`requirements.txt`に記載されています。
---

## 使い方

### GUIモードで起動

python main.py gui 


### コマンドラインから直接ダウンロードや変換も可能

python main.py download "https://www.youtube.com/watch?v=xxxx"
python main.py convert input.mp4 output.mp3

---

## ライセンス

MIT License

---

## 開発・連絡先

開発者: [yunfie_twitter](https://twitter.com/yunfie_twitter)  
GitHub: [https://github.com/yunfie-twitter/LiveLeaper](https://github.com/yunfie-twitter/LiveLeaper)

---
