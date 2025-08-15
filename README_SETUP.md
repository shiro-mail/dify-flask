# 環境設定ガイド

## 必要な環境変数の設定

このアプリケーションを実行するには、以下の環境変数を設定する必要があります。

### 1. .envファイルの作成

```bash
cp .env.example .env
```

### 2. .envファイルの編集

`.env`ファイルを開いて、以下の値を実際の値に置き換えてください：

```
DIFY_API_BASE_URL=https://api.dify.ai
DIFY_API_KEY=app-rn8gqMRYlEYkDH0rAntmbDJV
DIFY_WORKFLOW_ID=ed1cebe9-c907-4769-b1ac-e0e23aa6cff7
```

### 3. アプリケーションの起動

```bash
source venv/bin/activate
python app.py
```

## Dify HTTPリクエストノード設定

イテレーター処理を使用する場合、DifyワークフローのHTTPリクエストノードを以下のように設定してください：

- **Method**: POST
- **URL**: `http://127.0.0.1:5001/api/webhook/result`
- **Body Type**: JSON
- **Body Content**: 
```json
{
  "session_id": "{{session_id}}",
  "filename": "{{filename}}",
  "file_index": "{{file_index}}",
  "result": "{{analysis_result}}"
}
```

## 注意事項

- `.env`ファイルはGitにコミットしないでください（.gitignoreに含まれています）
- 本番環境では適切な環境変数管理システムを使用してください
