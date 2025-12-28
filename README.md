# pavlok_CLI_agent
<img src="./documents/images/README/warning.png" alt="warning" width="360">

## 🎥 Demo – Click to Play
こちらの画面例は実際のデモ動画です（再生するとYouTubeで開きます）

[![Demo Video](https://img.youtube.com/vi/WJdjTm0iQBY/0.jpg)](https://www.youtube.com/watch?v=WJdjTm0iQBY)

## Quick Start
⚠️`pavlok`端末を所有していることが前提になります⚠️

本レポジトリをローカルにcloneして環境構築(`uv sync`)し、
本レポジトリソースをカレントディレクトリにし`CLI Agent`,`IDE Agent`を起動すれば即機能します。

### 動作イメージ
![alt text](./documents/images/README/image5.png)

## 背景
私は意志が弱い人間のため
`悪習慣を自分の意思で辞め良い習慣を継続していく`
ということが`36年間`できていない。

また、私は他者に監視されることを嫌う人間のため、
`誰かに強制される`
ということに耐えられない。

この問題を解決するために世にある`コーチング支援`ツールを導入しても、
既製品では`強制力`が弱いため弱い自分に負けて辞めてしまうことを繰り返してきた。

本PJは、上記の問題を解決するために
`AI Agentにコーチング対象者へ行動を強制する権限`を付与することで
`自身で設定した目標`に対して矛盾しない行動、思考をするように`矯正`すること
を目的としている。


## 前提
- `uv`がインストール済みであること
- `CLI Agent` or `IDE Agent`が何か1つ以上インストール済みで利用可能なこと
  - CLI Agent
    - codex CLI: ⭕️動作確認済
    - claude code: ❌動作未確認
    - gemini CLI: ❌動作未確認
  - IDE Agent
    - VS code拡張機能
      - Codex – OpenAI’s coding agent: ⭕️動作確認済
      - Gemini Code Assist: ❌動作未確認
    - Cursor: ❌動作未確認

## 導入
### 1. pavlok本体を購入します
- [日本代理店](https://www.pavlok-japan-official.com/top)
- [本社](https://www.pavlok.com/)

### 2. `pavlokアカウント新規作成` & `pavlok本体とアカウント紐付け`を行います
   - [解説動画](https://video.wixstatic.com/video/3cbb88_fafe1dda81a346d48023698dbda68355/1080p/mp4/file.mp4)
### 3. pavlok公式サーバーから`API_KEY`を取得します
1. [pavlok公式_APIDOC](https://pavlok.readme.io/reference/intro/authentication)にアクセスします
2. `Log in to see your API keys`をクリックします
   ![alt text](./documents/images/README/image1.png)
3. メールアドレスを入力し、`Send LogIn Link`をクリックします
   ![alt text](./documents/images/README/image2.png)
4. メールが届くので`Log In`をクリックします
 ![alt text](./documents/images/README/image3.png)
5. Authページに`API_KEY`が表示されているのでコピーします **prefixの`Bearer `を除いたものが`PAVLOK_API_KEY`です**
   ![alt text](./documents/images/README/image4.png)
### 4. レポジトリのクローン
```bash
cd {your dir}
git clone https://github.com/motoya0118/pavlok_CLI_agent.git
```
### 5. .envの設定
`YOUR_API_KEY`部を取得した自身の`PAVLOK_API_KEY`に置き換えて、以下のコマンドを実行します
```bash
echo 'PAVLOK_API_KEY=YOUR_API_KEY' > .env
```

### 6. 仮装環境構築 & インストール
```bash
uv sync
```

### 7. コマンド実行例
刺激の種類と値を指定してAPIへリクエストできます（値は1〜100の範囲に限定されています）。

```bash
uv run main.py beep 100
```
