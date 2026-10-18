name: Run Gemini Video Pipeline Online

on:
  workflow_dispatch: # Bấm nút chạy thủ công trên GitHub
  schedule:
    - cron: '0 2 * * *' # Chạy định kỳ hàng ngày lúc 2:00 UTC

jobs:
  run-python-script:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python 3.10
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Run Video Generation Tool
        env:
          GEMINI_KEYS: ${{ secrets.GEMINI_KEYS }}
        run: |
          python video_generator_tool.py

      - name: Upload generated assets
        uses: actions/upload-artifact@v4
        with:
          name: video-assets-output
          path: output/