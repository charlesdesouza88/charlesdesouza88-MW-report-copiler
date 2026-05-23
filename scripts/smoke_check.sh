#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <base_url> [admin_password]"
  echo "Example: $0 https://your-app.up.railway.app misterwiz"
  exit 1
fi

BASE_URL="${1%/}"
ADMIN_PASSWORD="${2:-${ADMIN_PASSWORD:-}}"

if [[ -z "${ADMIN_PASSWORD}" ]]; then
  echo "ERROR: admin password is required (arg #2 or ADMIN_PASSWORD env var)."
  exit 1
fi

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

cookies_file="$tmp_dir/cookies.txt"
preview_file="$tmp_dir/preview.html"
one_file="$tmp_dir/one.html"
all_zip="$tmp_dir/all.zip"

echo "[1/6] Login"
login_http=$(curl -s -o "$tmp_dir/login.body" -w "%{http_code}" -c "$cookies_file" \
  -X POST -d "password=${ADMIN_PASSWORD}" "${BASE_URL}/login")
echo "login_http=${login_http}"
if [[ "$login_http" != "302" ]]; then
  echo "FAIL: login did not return 302 redirect"
  exit 1
fi

echo "[2/6] Upload CSVs"
upload_http=$(curl -s -o "$tmp_dir/upload.body" -w "%{http_code}" -b "$cookies_file" -c "$cookies_file" \
  -F "students=@data/students.csv;type=text/csv" \
  -F "lessons=@data/lessons.csv;type=text/csv" \
  "${BASE_URL}/upload")
echo "upload_http=${upload_http}"
if [[ "$upload_http" != "200" ]]; then
  echo "FAIL: upload did not return 200"
  exit 1
fi

echo "[3/6] Generate reports"
generate_http=$(curl -s -o "$tmp_dir/generate.body" -w "%{http_code}" -b "$cookies_file" -c "$cookies_file" \
  -X POST "${BASE_URL}/generate")
echo "generate_http=${generate_http}"
if [[ "$generate_http" != "302" ]]; then
  echo "FAIL: report generation did not return 302"
  exit 1
fi

echo "[4/6] Find and preview first report"
curl -s -b "$cookies_file" "${BASE_URL}/reports" > "$tmp_dir/reports.body"
report_name=$(awk '
  match($0, /\/reports\/preview\/[^"?]+/) {
    print substr($0, RSTART + 17, RLENGTH - 17)
    exit
  }
' "$tmp_dir/reports.body")

if [[ -z "$report_name" ]]; then
  echo "FAIL: could not discover report name from /reports"
  exit 1
fi

preview_http=$(curl -s -o "$preview_file" -w "%{http_code}" -b "$cookies_file" \
  "${BASE_URL}/reports/preview/${report_name}")
echo "preview_http=${preview_http} report=${report_name}"
if [[ "$preview_http" != "200" ]]; then
  echo "FAIL: preview did not return 200"
  exit 1
fi

echo "[5/6] Download single report"
one_http=$(curl -s -o "$one_file" -w "%{http_code}" -b "$cookies_file" \
  "${BASE_URL}/reports/download/${report_name}")
one_bytes=$(wc -c < "$one_file")
echo "download_one_http=${one_http} bytes=${one_bytes}"
if [[ "$one_http" != "200" || "$one_bytes" -le 0 ]]; then
  echo "FAIL: single report download failed"
  exit 1
fi

echo "[6/6] Download all zip"
all_http=$(curl -s -o "$all_zip" -w "%{http_code}" -b "$cookies_file" \
  "${BASE_URL}/reports/download-all")
all_bytes=$(wc -c < "$all_zip")
echo "download_all_http=${all_http} bytes=${all_bytes}"
if [[ "$all_http" != "200" || "$all_bytes" -le 0 ]]; then
  echo "FAIL: zip download failed"
  exit 1
fi

if command -v file >/dev/null 2>&1; then
  zip_type=$(file -b "$all_zip")
  echo "zip_file_type=${zip_type}"
fi

preview_head=$(head -n 1 "$preview_file")
echo "preview_head=${preview_head}"

echo "PASS: live smoke checklist completed for ${BASE_URL}"
