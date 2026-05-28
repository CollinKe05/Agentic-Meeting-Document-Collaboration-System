from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse
import shutil
import os
import threading
import uuid

from core.pdf2img import pdf_to_images
from core.pipeline_onnx import process_image
from core.markdown import to_markdown_v2

app = FastAPI()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

tasks = {}


# =========================
# 首页 UI
# =========================
@app.get("/", response_class=HTMLResponse)
def home():

    return """
    <html>
    <head>
        <title>DocAI V5.5 — ONNX</title>

        <style>

            body{
                font-family: Arial;
                padding:40px;
                background:#f5f5f5;
            }

            .card{
                background:white;
                padding:30px;
                border-radius:12px;
                box-shadow:0 2px 10px rgba(0,0,0,0.1);
            }

            button{
                background:#0078ff;
                color:white;
                border:none;
                padding:12px 20px;
                border-radius:8px;
                cursor:pointer;
                font-size:16px;
            }

            button:disabled{
                background:gray;
            }

            textarea{
                width:100%;
                height:400px;
                margin-top:20px;
            }

            #progress-container{
                width:100%;
                background:#ddd;
                border-radius:10px;
                margin-top:20px;
                overflow:hidden;
                display:none;
            }

            #progress-bar{
                width:0%;
                height:30px;
                background:#0078ff;
                text-align:center;
                color:white;
                line-height:30px;
                transition:0.3s;
            }

        </style>
    </head>

    <body>

        <div class="card">

            <h1>📄 DocAI 文档解析系统</h1>

            <input type="file" id="fileInput">

            <button id="uploadBtn"
                    onclick="upload()">
                    上传并解析
            </button>

            <div id="progress-container">
                <div id="progress-bar">
                    0%
                </div>
            </div>

            <h3 id="status"></h3>

            <textarea id="out"></textarea>

        </div>

        <script>

        async function upload() {

            let file =
                document.getElementById("fileInput").files[0];

            if(!file){
                alert("请选择文件");
                return;
            }

            let btn =
                document.getElementById("uploadBtn");

            btn.disabled = true;

            document.getElementById(
                "status"
            ).innerText = "⏳ 正在处理文档...";

            document.getElementById(
                "progress-container"
            ).style.display = "block";

            let form = new FormData();
            form.append("file", file);

            let res = await fetch("/upload", {
                method: "POST",
                body: form
            });

            let data = await res.json();
            let task_id = data.task_id;

            let timer = setInterval(async () => {

                let r =
                    await fetch("/progress/" + task_id);

                let d = await r.json();

                let progress =
                    d.progress || 0;

                let bar =
                    document.getElementById(
                        "progress-bar"
                    );

                bar.style.width =
                    progress + "%";

                bar.innerText =
                    progress + "%";

                if(d.status === "done"){

                    clearInterval(timer);

                    document.getElementById(
                        "status"
                    ).innerText =
                    "✅ 处理完成";

                    document.getElementById(
                        "out"
                    ).value =
                    d.result;

                    btn.disabled = false;
                }

                if(d.status === "error"){

                    clearInterval(timer);

                    document.getElementById(
                        "status"
                    ).innerText =
                    "❌ 处理失败";

                    document.getElementById(
                        "out"
                    ).value =
                    d.error;

                    btn.disabled = false;
                }

            }, 500);

        }

        </script>

    </body>
    </html>
    """


# =========================
# 上传接口
# =========================
@app.post("/upload")
async def upload(file: UploadFile = File(...)):

    task_id = str(uuid.uuid4())

    tasks[task_id] = {
        "progress": 0,
        "status": "running",
        "result": None,
        "error": None
    }

    file_path = f"{UPLOAD_DIR}/{file.filename}"

    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    thread = threading.Thread(
        target=run_task,
        args=(task_id, file_path, file.filename)
    )
    thread.start()

    return {"task_id": task_id}


# =========================
# 后台任务执行
# =========================
def run_task(task_id, file_path, filename):

    try:

        if filename.lower().endswith(".pdf"):

            tasks[task_id]["progress"] = 10

            pages = pdf_to_images(file_path)

            tasks[task_id]["progress"] = 20

            all_blocks = []

            total = len(pages)

            for i, p in enumerate(pages):

                blocks = process_image(p)

                all_blocks.extend(blocks)

                progress = 20 + int(
                    (i + 1) / total * 60
                )

                tasks[task_id]["progress"] = progress

            tasks[task_id]["progress"] = 85

        else:

            tasks[task_id]["progress"] = 10

            all_blocks = process_image(file_path)

            tasks[task_id]["progress"] = 85

        md = to_markdown_v2(all_blocks)

        tasks[task_id]["progress"] = 95

        tasks[task_id]["result"] = md
        tasks[task_id]["status"] = "done"
        tasks[task_id]["progress"] = 100

    except Exception as e:

        tasks[task_id]["status"] = "error"
        tasks[task_id]["error"] = str(e)


# =========================
# 进度查询接口
# =========================
@app.get("/progress/{task_id}")
def get_progress(task_id: str):

    return tasks.get(task_id, {
        "status": "not_found",
        "progress": 0
    })
