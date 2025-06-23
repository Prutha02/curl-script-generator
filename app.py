import json
import subprocess
import sys
import time
from pathlib import Path
from extract_curl import process_extracted_curls, generate_requests_from_json
import streamlit as st

st.set_page_config(page_title="cURL Extractor", layout="wide")

st.title("cURL Request Extractor")
st.markdown("Paste one or more `curl` commands below:")

user_input = st.text_area("Paste your cURL commands here", height=300)
extracted_data_dir = "extracted_data"
output_script_path = "../python_request.py"

if "script_ran" not in st.session_state:
    st.session_state["script_ran"] = False

if st.button("Process cURL"):
    if user_input.strip():
        content = user_input.replace("\\\n", " ").replace("^\n", " ")
        extracted_data = process_extracted_curls(content, extracted_data_dir)
        st.session_state["extracted_data"] = extracted_data
        st.session_state["curl_processed"] = True
        st.success("✅ cURL commands processed and saved.")
    else:
        st.warning("⚠️ Please paste at least one cURL command.")

if st.session_state.get("curl_processed"):
    extracted_data = st.session_state.get("extracted_data", {})

    st.sidebar.header("🔍 View Extracted Category")
    selected_key = st.sidebar.selectbox("Select a category:", list(extracted_data.keys()))
    st.sidebar.markdown(f"### `{selected_key}` Preview")

    if extracted_data[selected_key]:
        for i, item in enumerate(extracted_data[selected_key]):
            st.sidebar.json(item)
            if i >= 2:
                break
    else:
        st.sidebar.write("No data in this category.")

    st.title("🛠️ Generate Python Request")

    def load_json(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    headers_list = load_json(f"{extracted_data_dir}/headers.json")
    cookies_list = load_json(f"{extracted_data_dir}/cookies.json")
    query_params_list = load_json(f"{extracted_data_dir}/query_params.json")
    body_params_list = load_json(f"{extracted_data_dir}/body_params.json")
    form_data_list = load_json(f"{extracted_data_dir}/form_data.json")
    json_data_list = load_json(f"{extracted_data_dir}/json_data.json")
    meta_list = load_json(f"{extracted_data_dir}/meta.json")

    if not meta_list:
        st.warning("⚠️ No requests found.")
        st.stop()

    st.markdown(f"**Total Requests Found:** {len(meta_list)}")

    include_requests = []
    use_cookies_list = []
    use_proxy_list = []
    use_curl_cffi_list = []
    search_texts = []

    def handle_include_change(idx):
        if st.session_state.get(f"include_{idx}", False):
            st.session_state[f"expander_{idx}"] = True

    for idx, meta in enumerate(meta_list):
        include_key = f"include_{idx}"
        expander_key = f"expander_{idx}"
        st.session_state.setdefault(expander_key, False)
        st.session_state.setdefault(include_key, False)

        with st.expander(f"Request #{idx + 1}: {meta['method']} {meta['url']}", expanded=st.session_state[expander_key]):
            st.checkbox(
                "✅ Include this request?",
                key=include_key,
                on_change=handle_include_change,
                args=(idx,)
            )

            include = st.session_state[include_key]
            include_requests.append(include)

            if include:
                cookies = st.checkbox("🍪 Use cookies?", key=f"cookies_{idx}")
                proxy = st.checkbox("🛡️ Use proxy?", key=f"proxy_{idx}")
                cffi = st.checkbox("⚡ Use curl_cffi (if no request)?", key=f"cffi_{idx}")
                search = st.text_input("🔍 Text to search in response (optional):", key=f"search_{idx}")
            else:
                cookies = proxy = cffi = False
                search = ""

            use_cookies_list.append(cookies)
            use_proxy_list.append(proxy)
            use_curl_cffi_list.append(cffi)
            search_texts.append(search)

    st.subheader("🌐 Proxy Settings")
    proxy_url = st.text_input("🛡️ Proxy URL (e.g., http://user:pass@host:port)", value="")

    st.subheader("🥪 Execution Settings")
    total_runs = st.number_input("🔁 Number of times to run all requests", min_value=1, value=1)
    threads = st.number_input("🔧 Number of threads to use", min_value=1, value=1)

    if st.button("🚀 Generate Python Script", disabled=st.session_state["script_ran"]):
        if not any(include_requests):
            st.warning("⚠️ You must include at least one request.")
            st.stop()
        try:
            generate_requests_from_json(
                headers_file=f"{extracted_data_dir}/headers.json",
                cookies_file=f"{extracted_data_dir}/cookies.json",
                query_params_file=f"{extracted_data_dir}/query_params.json",
                body_params_file=f"{extracted_data_dir}/body_params.json",
                form_data_file=f"{extracted_data_dir}/form_data.json",
                json_data_file=f"{extracted_data_dir}/json_data.json",
                meta_file=f"{extracted_data_dir}/meta.json",
                output_file=output_script_path,
                include_requests=include_requests,
                use_cookies_list=use_cookies_list,
                use_proxy_list=use_proxy_list,
                use_curl_cffi_list=use_curl_cffi_list,
                search_texts=search_texts,
                total_runs=total_runs,
                threads=threads,
                report_filename="report.xlsx",
                proxy_url=proxy_url
            )

            st.success(f"✅ Script generated: `{output_script_path}`")

            with open(output_script_path, "r", encoding="utf-8") as f:
                code = f.read()
            st.code(code, language="python")

            st.download_button("📅 Download Script", code, file_name="generated_script.py", mime="text/x-python")

            st.session_state["script_generated"] = True
            # st.session_state["script_ran"] = True

        except Exception as e:
            st.error(f"❌ Error: {e}")

if st.session_state.get("script_generated"):
    st.markdown("### ▶️ Run Script")

    if st.button("▶️ Run now", key="run_script"):
        try:
            with st.status("🚀 Running script...", expanded=True) as status:
                venv_python = (
                    Path(".venv") / "Scripts" / "python.exe" if sys.platform == "win32"
                    else Path(".venv") / "bin" / "python"
                )
                if not venv_python.exists():
                    venv_python = "python"

                python_exec = sys.executable
                start_time = time.time()

                st.write("### 📤 Output:")
                output_container = st.empty()

                process = subprocess.Popen(
                    [python_exec, "-u", output_script_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True,
                    bufsize=1
                )

                live_output = ""
                for line in process.stdout:
                    live_output += line
                    output_container.code(live_output, language="bash")

                process.stdout.close()
                return_code = process.wait()
                elapsed = round(time.time() - start_time, 2)

                if return_code == 0:
                    st.success(f"✅ Script executed in {elapsed} seconds.")
                else:
                    st.error(f"❌ Script exited with code {return_code}")

            report_path = Path("report.xlsx")
            if report_path.exists():
                with open(report_path, "rb") as f:
                    st.download_button(
                        "📅 Download Excel Report",
                        f,
                        file_name="report.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
            else:
                st.warning("⚠️ Report file not found.")

            st.session_state["script_ran"] = False

        except Exception as e:
            st.error(f"❌ Error running script: {e}")


