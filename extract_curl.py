import glob
import os
import re
import urllib.parse
from datetime import datetime
import textwrap
import shlex
import urllib.parse
import json


def extract_curl(curl_command):
    tokens = shlex.split(curl_command)
    headers = {}
    cookies = {}
    query_params = {}
    body_params = {}
    json_data = {}
    form_data = {}
    method = "GET"
    url = None
    method_explicit = False

    i = 0
    while i < len(tokens):
        token = tokens[i]

        # URL
        if token.startswith("http"):
            parsed_url = urllib.parse.urlparse(token)
            url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
            query_params = dict(urllib.parse.parse_qsl(parsed_url.query))

        # HTTP Method
        elif token in ['-X', '--request']:
            method = tokens[i + 1].upper()
            method_explicit = True
            i += 1

        # Header
        elif token == '-H' or token.startswith('-H'):
            header = token[2:] if token.startswith('-H') and len(token) > 2 else tokens[i + 1]
            if ':' in header:
                key, value = map(str.strip, header.split(':', 1))
                if key.lower() == 'cookie':
                    for cookie in value.split(';'):
                        if '=' in cookie:
                            c_key, c_val = cookie.strip().split('=', 1)
                            cookies[c_key] = c_val
                else:
                    headers[key] = value
            if not token.startswith('-H'):
                i += 1

        # Cookie
        elif token in ['-b', '--cookie'] or token.startswith('-b'):
            cookie_val = token[2:] if token.startswith('-b') and len(token) > 2 else tokens[i + 1]
            for cookie in cookie_val.split(';'):
                if '=' in cookie:
                    c_key, c_val = cookie.strip().split('=', 1)
                    cookies[c_key] = c_val
            if not token.startswith('-b'):
                i += 1

        # Body
        elif token in ['--data', '--data-raw', '--data-urlencode', '--data-binary', '-d']:
            data_val = tokens[i + 1]
            headers_lower = {k.lower(): v for k, v in headers.items()}
            content_type = headers_lower.get("content-type", "")
            if not method_explicit:
                method = "POST"

            try:
                parsed = json.loads(data_val)
                if "application/json" in content_type and isinstance(parsed, (dict, list)):
                    json_data = parsed
                else:
                    body_params.update(urllib.parse.parse_qsl(data_val))
            except json.JSONDecodeError:
                body_params.update(urllib.parse.parse_qsl(data_val))
            i += 1

        # Multipart
        elif token == '-F':
            form_val = tokens[i + 1]
            if '=' in form_val:
                k, v = form_val.split('=', 1)
                form_data[k] = v
            if not method_explicit:
                method = "POST"
            i += 1

        i += 1

    return {
        "url": url,
        "method": method,
        "headers": headers,
        "cookies": cookies,
        "query_params": query_params,
        "body_params": body_params,
        "json_data": json_data,
        "form_data": form_data
    }


def process_extracted_curls(content, extracted_data_dir="extracted_data"):
    os.makedirs(extracted_data_dir, exist_ok=True)

    curl_blocks = re.split(r'\bcurl\b', content)
    curl_blocks = [f'curl {block.strip()}' for block in curl_blocks if block.strip()]

    categories = {
        "headers": [],
        "cookies": [],
        "query_params": [],
        "body_params": [],
        "form_data": [],
        "json_data": [],
        "meta": []
    }

    for idx, curl_cmd in enumerate(curl_blocks, 1):
        try:
            result = extract_curl(curl_cmd)
            for key in categories.keys():
                if key == "meta":
                    categories[key].append({
                        "method": result.get("method", ""),
                        "url": result.get("url", "")
                    })
                elif key == "json_data":
                    headers = result.get("headers", {})
                    headers_lower = {k.lower(): v for k, v in headers.items()}
                    content_type = headers_lower.get("content-type", "")
                    body = result.get("json_data", {})
                    if "application/json" in content_type and isinstance(body, dict):
                        categories[key].append(body)
                    else:
                        categories[key].append({})
                elif key == "body_params":
                    body = result.get("body_params", {})
                    fallback_data = body if not isinstance(body, dict) or any(isinstance(v, str) for v in body.values()) else {}
                    categories[key].append(fallback_data)
                else:
                    categories[key].append(result.get(key, {}))
            print(f"[✓]  Parsed curl #{idx}")
        except Exception as e:
            print(f"[X] Error parsing curl #{idx}:", e)

    saved_data = {}
    for key, data in categories.items():
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{extracted_data_dir}/{key}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        saved_data[key] = data

    print("✅ All JSON files saved.")
    return saved_data


def get_latest_file(directory, prefix):
    pattern = os.path.join(directory, f"{prefix}_*.json")
    files = glob.glob(pattern)
    if not files:
        raise FileNotFoundError(f"No files found for prefix: {prefix}")
    latest_file = max(files, key=os.path.getmtime)
    return latest_file


def generate_requests_from_json(
    headers_file, cookies_file, query_params_file, body_params_file,
    form_data_file, json_data_file, meta_file, output_file,
    include_requests, use_cookies_list, use_proxy_list,
    use_curl_cffi_list, search_texts, total_runs=1, threads=5,
    report_filename="report.xlsx", response_dir="saved_pages"
):
    with open(headers_file, "r", encoding="utf-8") as f:
        headers_list = json.load(f)
    with open(cookies_file, "r", encoding="utf-8") as f:
        cookies_list = json.load(f)
    with open(query_params_file, "r", encoding="utf-8") as f:
        query_params_list = json.load(f)
    with open(body_params_file, "r", encoding="utf-8") as f:
        body_params_list = json.load(f)
    with open(form_data_file, "r", encoding="utf-8") as f:
        form_data_list = json.load(f)
    with open(json_data_file, "r", encoding="utf-8") as f:
        json_data_list = json.load(f)
    with open(meta_file, "r", encoding="utf-8") as f:
        meta_list = json.load(f)

    os.makedirs(response_dir, exist_ok=True)

    script_lines = [
        "import json",
        "import urllib.parse",
        "from datetime import datetime",
        "from concurrent.futures import ThreadPoolExecutor, as_completed",
        "import time",
        "import pandas as pd\n",
        "requests_list = []",
        "results = []\n"
    ]

    for idx, meta in enumerate(meta_list):
        if not include_requests[idx]:
            print(f"Skipping request #{idx + 1}")
            continue

        method = meta["method"].lower()
        url = meta["url"]
        use_cookies = use_cookies_list[idx]
        use_proxy = use_proxy_list[idx]
        use_curl_cffi = use_curl_cffi_list[idx]
        search_text = search_texts[idx]

        import_line = "from curl_cffi import requests" if use_curl_cffi else "import requests"
        impersonate_line = ", impersonate='chrome99'" if use_curl_cffi else ""

        if import_line not in script_lines:
            script_lines.insert(0, import_line)

        headers = headers_list[idx]
        cookies = cookies_list[idx] if use_cookies else {}
        params = query_params_list[idx]
        body_data = body_params_list[idx]
        files = form_data_list[idx]
        json_data = json_data_list[idx]
        domain = urllib.parse.urlparse(url).netloc.replace('.', '_')

        req_code = []
        req_code.append(f"def request_{idx}():")
        req_code.append(f"    url = {json.dumps(url)}")
        req_code.append(f"    params = {params}")
        req_code.append(f"    headers = {headers}" if headers else "    headers = {}")
        req_code.append(f"    cookies = {cookies}" if cookies else "    cookies = {}")
        req_code.append(f"    files = {files}")
        req_code.append(f"    text_to_search = {json.dumps(search_text)}")

        if use_proxy:
            req_code.append("    token = \"f42a5b59aec3467e97a8794c611c436b915896\"")
            req_code.append("    proxyModeUrl = \"http://{}:super=true@proxy.scrape.do:8080\".format(token)")
            req_code.append("    proxies = {\"http\": proxyModeUrl, \"https\": proxyModeUrl}")

        req_code.append("    start_time = time.time()")

        request_args = "url, params=params, headers=headers, cookies=cookies"
        if json_data:
            req_code.append(f"    data = {json.dumps(json_data)}")
            req_code.append("    headers.pop('content-type', None)")
            request_args += ", json=data"
        else:
            req_code.append(f"    data = {body_data}")
            request_args += ", data=data"

        request_args += ", files=files"
        if use_proxy:
            request_args += ", proxies=proxies, verify=False"
        request_args += impersonate_line

        req_code.append(f"    response = requests.{method}({request_args})")
        # req_code.append(f"    print(response.status_code)")
        req_code.append("    end_time = time.time()")
        req_code.append("    elapsed = round(end_time - start_time, 2)")
        req_code.append("    matched = 'Yes' if not text_to_search or text_to_search in response.text else 'No'")
        req_code.append("    results.append({")
        req_code.append("        'url': url,")
        req_code.append("        'status_code': response.status_code,")
        req_code.append("        'status': 'Success' if response.status_code == 200 else 'Failed',")
        req_code.append("        'time_taken': elapsed,")
        req_code.append("        'text_matched': matched")
        req_code.append("    })")

        req_code.append("    if response.status_code == 200 and matched == 'Yes':")
        req_code.append("        content_type = response.headers.get('Content-Type', '')")
        req_code.append("        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')")

        req_code.append(f"        file_prefix = '{response_dir}/response_{domain}_' + timestamp + '_{idx}'")
        req_code.append("        if 'application/json' in content_type:")
        req_code.append("            with open(file_prefix + '.json', 'w', encoding='utf-8') as f:")
        req_code.append("                json.dump(response.json(), f, ensure_ascii=False, indent=4)")
        req_code.append("        elif 'text/html' in content_type:")
        req_code.append("            with open(file_prefix + '.html', 'w', encoding='utf-8') as f:")
        req_code.append("                f.write(response.text)")
        req_code.append("        else:")
        req_code.append("            with open(file_prefix + '.txt', 'w', encoding='utf-8') as f:")
        req_code.append("                f.write(response.text)")
        # req_code.append("        print(f'Saved to {file_prefix}')")
        # req_code.append("    else:")
        # req_code.append("        print('Request failed or text not matched.')")
        req_code.append("")

        script_lines.extend(req_code)
        script_lines.append(f"requests_list.append(request_{idx})")

    # Main execution block
    main_block = f"""
if __name__ == "__main__":
    total_runs = {total_runs}
    threads = {threads}
    report_filename = {json.dumps(report_filename)}

    expanded_requests = []
    for _ in range(total_runs):
        expanded_requests.extend(requests_list)

    with ThreadPoolExecutor(max_workers=threads) as executor:
        futures = {{
            executor.submit(request): i for i, request in enumerate(expanded_requests)
        }}

        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"Error in thread: {{e}}")

    df = pd.DataFrame(results)
    df.to_excel(report_filename, index=False)
    # print(f"Excel report saved as '{{report_filename}}'")
    print("All requests completed.")
"""
    script_lines.append(textwrap.dedent(main_block))

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(script_lines))

    print(f"\nGenerated {output_file}.")

