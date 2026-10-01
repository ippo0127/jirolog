# 誤りの報告の中継（Cloudflare Workers）

サイトの「誤りを報告」フォームから送られた内容を、**非公開リポジトリ**（例: `jirolog-reports`）の GitHub Issue（ラベル `report`）にする小さなプログラムです。報告の中身はサイトを見る人には見えません。無料プランで動きます。トークンはこの Worker の中にだけ置き、サイト（ブラウザ側）には出しません。

## 設定のしかた（一度だけ）

1. **GitHub のトークンを作る**
   GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token
   - Repository access: **Only select repositories** で報告用の非公開リポジトリ（`jirolog-reports`）だけを選ぶ
   - Permissions → Repository permissions → **Issues: Read and write**（ほかは付けない）
   - 作ったトークンは次の手順で Cloudflare に貼るだけにして、ほかには保存しない
2. **Worker を作る**
   Cloudflare ダッシュボード → Workers & Pages → Create → Worker（名前は例: `jirolog-report`）→ Deploy → Edit code
   - `worker.js` の中身を全部貼り付けて Deploy
3. **変数を入れる**（Worker → Settings → Variables and Secrets）
   - `GITHUB_REPO`（Text）: `ユーザー名/jirolog-reports`（報告用の非公開リポジトリ）
   - `ALLOWED_ORIGINS`（Text）: サイトの URL（例: `https://ユーザー名.github.io`）
   - `GITHUB_TOKEN`（**Secret**）: 手順1のトークン
4. **サイトにつなぐ**
   Worker の URL（例: `https://jirolog-report.xxxx.workers.dev`）を `data/site.json` の `report_endpoint` に入れて作り直すと、報告フォームに「送信する」ボタンが出る。

## 届いた報告の処理

定期実行の Claude が `docs/process-reports.md` の手順で処理する。情報源で確かめられたものだけを直して公開し、Issue を閉じる。確かめられないものは `needs-review` ラベルを付けて残す。
