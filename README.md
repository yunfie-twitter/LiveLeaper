# LiveLeaper 🎥

![LiveLeaper](https://img.shields.io/badge/LiveLeaper-YouTube%20Downloader-blue)

**LiveLeaper** は、YouTube や ニコニコ動画 などから動画・音声を簡単にダウンロード＆変換できる、**Python製の高機能GUIツール**です。個人利用から技術学習まで、様々な用途に対応しています。

---

## 📚 目次

- [主な機能](#主な機能)
- [インストール方法](#インストール方法)
- [使い方](#使い方)
- [対応フォーマット](#対応フォーマット)
- [貢献について](#貢献について)
- [ライセンス](#ライセンス)
- [お問い合わせ](#お問い合わせ)
- [リリース情報](#リリース情報)

---

## 🔧 主な機能

- ✅ **URL自動修正機能**（YouTube・ニコニコ動画対応）
- ✅ **動画・音声の変換と保存**（MP4, MP3, AAC などに対応）
- ✅ **直感的なGUI**（PyQt5ベース）
- ✅ **バッチ処理・並列ダウンロード対応**
- ✅ **ハードウェアエンコード対応**（NVIDIA NVENC・Intel QSVなど）
- ✅ **初期設定ウィザード付き**
- ✅ **ログ表示・進捗状況バーあり**
- ✅ **クロスプラットフォーム対応**（Windows / Linux / macOS）

---

## 🧩 インストール方法

Python 3.8 以上が必要です。以下の手順でセットアップしてください：

```bash
git clone https://github.com/yunfie-twitter/LiveLeaper.git
cd LiveLeaper
pip install -r requirements.txt
```

---

## ▶️ 使い方

### GUIモードの起動

```bash
python main.py gui
```

> 💡 **Windowsユーザーはインストーラー版で簡単にセットアップ可能です。**

### コマンドラインモード

```bash
python main.py download "https://www.youtube.com/watch?v=xxxx"
python main.py convert input.mp4 output.mp3
```

---

## 🎵 対応フォーマット

- **MP4**（高画質動画）
- **MP3**（音声のみ）
- **AAC**, **WAV** など、変換元の品質に応じて対応

---

## 🤝 貢献について

貢献は大歓迎です！以下の手順でプルリクエストをお送りください：

```bash
# フォークして新しいブランチを作成
git checkout -b feature/YourFeature

# 変更をコミット
git commit -m "Add YourFeature"

# プッシュしてプルリクエストを作成
git push origin feature/YourFeature
```

---

## 📄 ライセンス

このプロジェクトは  
**GNU Affero 一般公衆ライセンス（AGPL） v3** の下で公開されています。  

> 🔗 ライセンス全文（日本語訳）:  
> [https://www.gnu.org/licenses/agpl-3.0.ja.html](https://www.gnu.org/licenses/agpl-3.0.ja.html)  
>  
> このライセンスの下では、**サーバー上で動作するプログラムを第三者に提供する場合も、ソースコードの公開が求められます。**

- このリポジトリは **v1.1.0以降、AGPLv3** ライセンスで提供されています。
- **v1.1.0以前はApache License 2.0** のもとで公開されており、それに基づくフォークや使用は引き続き有効です。
---

## 📬 お問い合わせ

- **開発者**：[yunfie_twitter](https://twitter.com/yunfie_twitter)  
- **GitHub**：[https://github.com/yunfie-twitter/LiveLeaper](https://github.com/yunfie-twitter/LiveLeaper)

---

## 🚀 リリース情報

最新版のダウンロードや更新履歴は以下から確認できます：  
🔗 [リリースページを見る](https://github.com/yunfie-twitter/LiveLeaper/releases)

---

💡 ご利用ありがとうございます！LiveLeaper があなたのダウンロードライフをより快適にしますように。
