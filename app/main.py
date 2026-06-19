from datetime import datetime, timezone
from html import escape
from random import choice, randint, uniform
from secrets import compare_digest
from time import perf_counter
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from pydantic import BaseModel, Field


app = FastAPI(
    title="Project MedGenome Operations API",
    description="Research workload dashboard and API for genomics operations.",
    version="2.0.0",
)

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin"
SESSION_COOKIE = "medgenome_session"
SESSION_VALUE = "medgenome-admin-session"

REQUESTS = Counter("medgenome_http_requests_total", "HTTP requests", ["method", "path", "status"])
LATENCY = Histogram("medgenome_http_request_seconds", "HTTP request latency", ["path"])
ACTIVE_JOBS = Gauge("medgenome_active_jobs", "Active genomics compute jobs")
DATASET_PB = Gauge("medgenome_dataset_petabytes", "Managed genomic data in petabytes")
FAILED_JOBS = Counter("medgenome_failed_jobs_total", "Failed genomics jobs")
UPLOADS = Counter("medgenome_uploads_total", "Uploaded genomic datasets")
UPLOADED_BYTES = Counter("medgenome_uploaded_bytes_total", "Uploaded genomic dataset bytes")
DATASETS = Gauge("medgenome_datasets_total", "Registered genomic datasets")


class Workload(BaseModel):
    id: str
    study: str
    pipeline: Literal["WGS", "RNA-Seq", "Variant Calling", "GWAS", "Pharma Cohort"]
    status: Literal["queued", "running", "completed", "failed"]
    samples: int = Field(ge=1)
    region: str
    compute_hours: float


class Dataset(BaseModel):
    id: str
    filename: str
    study: str
    file_type: str
    owner: str
    size_bytes: int
    uploaded_at: str
    linked_workload: str


WORKLOADS: list[Workload] = [
    Workload(id="MG-1001", study="Rare Disease Trio", pipeline="WGS", status="running", samples=240, region="us-east", compute_hours=184.2),
    Workload(id="MG-1002", study="Oncology Biomarker Discovery", pipeline="Variant Calling", status="queued", samples=880, region="eu-west", compute_hours=0),
    Workload(id="MG-1003", study="Population Genomics", pipeline="GWAS", status="completed", samples=5200, region="ap-south", compute_hours=1490.5),
    Workload(id="MG-1004", study="Transcriptomics Batch A", pipeline="RNA-Seq", status="running", samples=420, region="us-east", compute_hours=96.4),
]

DATASET_REGISTRY: list[Dataset] = [
    Dataset(
        id="DS-7001",
        filename="rare-disease-trio.fastq.gz",
        study="Rare Disease Trio",
        file_type="FASTQ",
        owner="Boston Children's Research",
        size_bytes=842_530_112,
        uploaded_at="2026-06-18T08:15:00+00:00",
        linked_workload="MG-1001",
    ),
    Dataset(
        id="DS-7002",
        filename="population-gwas.vcf.gz",
        study="Population Genomics",
        file_type="VCF",
        owner="Global Cohort Alliance",
        size_bytes=1_902_716_928,
        uploaded_at="2026-06-18T09:40:00+00:00",
        linked_workload="MG-1003",
    ),
]


@app.middleware("http")
async def record_metrics(request: Request, call_next):
    start = perf_counter()
    response = await call_next(request)
    path = request.url.path
    LATENCY.labels(path=path).observe(perf_counter() - start)
    REQUESTS.labels(method=request.method, path=path, status=response.status_code).inc()
    return response


def is_authenticated(request: Request) -> bool:
    return compare_digest(request.cookies.get(SESSION_COOKIE, ""), SESSION_VALUE)


def require_login(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=303)
    return None


def format_bytes(size_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    value = float(size_bytes)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.2f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size_bytes} B"


def total_dataset_bytes() -> int:
    return sum(item.size_bytes for item in DATASET_REGISTRY)


def platform_summary() -> dict:
    running = sum(1 for item in WORKLOADS if item.status == "running")
    queued = sum(1 for item in WORKLOADS if item.status == "queued")
    completed = sum(1 for item in WORKLOADS if item.status == "completed")
    failed = sum(1 for item in WORKLOADS if item.status == "failed")
    samples = sum(item.samples for item in WORKLOADS)
    compute_hours = round(sum(item.compute_hours for item in WORKLOADS), 2)
    active_jobs = running + queued
    dataset_bytes = total_dataset_bytes()
    dataset_petabytes = round(dataset_bytes / 1024**5, 8)
    ACTIVE_JOBS.set(active_jobs)
    DATASET_PB.set(dataset_petabytes)
    DATASETS.set(len(DATASET_REGISTRY))
    return {
        "active_jobs": active_jobs,
        "running_jobs": running,
        "queued_jobs": queued,
        "completed_jobs": completed,
        "failed_jobs": failed,
        "samples_processed": samples,
        "dataset_count": len(DATASET_REGISTRY),
        "dataset_bytes": dataset_bytes,
        "dataset_size": format_bytes(dataset_bytes),
        "dataset_petabytes": dataset_petabytes,
        "compute_hours": compute_hours,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


def page_shell(title: str, body: str) -> str:
    return f"""
    <!doctype html>
    <html lang="en">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>{title}</title>
      <style>
        :root {{
          --ink: #14213d;
          --muted: #64748b;
          --line: #d7dee8;
          --panel: #ffffff;
          --page: #eef3f8;
          --navy: #10324f;
          --teal: #007c89;
          --green: #1f9d63;
          --gold: #c47f00;
          --red: #b42318;
        }}
        * {{ box-sizing: border-box; }}
        body {{
          margin: 0;
          font-family: "Avenir Next", "Segoe UI", sans-serif;
          background:
            linear-gradient(120deg, rgba(0,124,137,.12), transparent 34%),
            linear-gradient(230deg, rgba(196,127,0,.10), transparent 30%),
            var(--page);
          color: var(--ink);
        }}
        a {{ color: inherit; }}
        .topbar {{
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 20px;
          padding: 18px 32px;
          background: rgba(255,255,255,.88);
          border-bottom: 1px solid var(--line);
          backdrop-filter: blur(14px);
          position: sticky;
          top: 0;
          z-index: 2;
        }}
        .brand {{ display: flex; flex-direction: column; gap: 2px; }}
        .brand strong {{ font-size: 18px; letter-spacing: .02em; }}
        .brand span {{ color: var(--muted); font-size: 13px; }}
        .nav {{ display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }}
        .nav a, button {{
          border: 1px solid var(--line);
          background: white;
          border-radius: 8px;
          padding: 10px 13px;
          font-weight: 700;
          text-decoration: none;
          cursor: pointer;
        }}
        .nav .primary, button.primary {{ background: var(--teal); border-color: var(--teal); color: white; }}
        .hero {{
          min-height: 230px;
          display: grid;
          align-items: end;
          padding: 54px 32px 32px;
          color: white;
          background:
            linear-gradient(90deg, rgba(16,50,79,.96), rgba(16,50,79,.72)),
            repeating-linear-gradient(115deg, rgba(255,255,255,.08) 0 1px, transparent 1px 18px),
            #10324f;
        }}
        .hero h1 {{ margin: 0; font-size: clamp(34px, 5vw, 64px); line-height: 1; max-width: 980px; }}
        .hero p {{ max-width: 740px; font-size: 17px; color: #d9e7ef; }}
        main {{ padding: 28px 32px 44px; max-width: 1440px; margin: 0 auto; }}
        .grid {{ display: grid; grid-template-columns: repeat(4, minmax(170px, 1fr)); gap: 16px; margin-bottom: 22px; }}
        .metric, .panel {{
          background: rgba(255,255,255,.92);
          border: 1px solid var(--line);
          border-radius: 8px;
          box-shadow: 0 18px 45px rgba(20,33,61,.08);
        }}
        .metric {{ padding: 18px; }}
        .metric span {{ color: var(--muted); font-size: 13px; font-weight: 700; text-transform: uppercase; }}
        .metric strong {{ display: block; margin-top: 8px; font-size: 30px; }}
        .layout {{ display: grid; grid-template-columns: minmax(300px, 420px) 1fr; gap: 20px; align-items: start; }}
        .panel {{ padding: 20px; overflow: hidden; }}
        .panel h2 {{ margin: 0 0 14px; font-size: 20px; }}
        form {{ display: grid; gap: 12px; }}
        label {{ display: grid; gap: 6px; color: var(--muted); font-weight: 700; font-size: 13px; }}
        input, select {{
          width: 100%;
          border: 1px solid var(--line);
          border-radius: 8px;
          padding: 11px 12px;
          font: inherit;
          background: white;
        }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 12px 10px; border-bottom: 1px solid #e6edf4; text-align: left; font-size: 14px; vertical-align: top; }}
        th {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }}
        .status {{ display: inline-flex; border-radius: 999px; padding: 5px 9px; font-size: 12px; font-weight: 800; }}
        .running {{ background: #dff7e9; color: #12643f; }}
        .queued {{ background: #fff2c7; color: #7a5100; }}
        .completed {{ background: #dceeff; color: #144f8c; }}
        .failed {{ background: #ffe0dd; color: #9a1c12; }}
        .login {{
          min-height: 100vh;
          display: grid;
          grid-template-columns: 1.2fr .8fr;
        }}
        .login-art {{
          background:
            linear-gradient(120deg, rgba(16,50,79,.92), rgba(0,124,137,.72)),
            repeating-linear-gradient(45deg, rgba(255,255,255,.10) 0 1px, transparent 1px 22px);
          color: white;
          padding: 54px;
          display: flex;
          flex-direction: column;
          justify-content: flex-end;
        }}
        .login-art h1 {{ font-size: clamp(40px, 6vw, 76px); line-height: .95; margin: 0 0 18px; }}
        .login-card {{ display: grid; place-items: center; padding: 32px; }}
        .login-card .panel {{ width: min(420px, 100%); }}
        .error {{ color: var(--red); font-weight: 800; }}
        @media (max-width: 920px) {{
          .grid, .layout, .login {{ grid-template-columns: 1fr; }}
          .topbar {{ align-items: flex-start; flex-direction: column; }}
          .hero {{ padding: 42px 20px 26px; }}
          main {{ padding: 20px; }}
          .login-art {{ min-height: 42vh; padding: 34px; }}
          table {{ min-width: 760px; }}
          .table-wrap {{ overflow-x: auto; }}
        }}
      </style>
    </head>
    <body>{body}</body>
    </html>
    """


def login_page(error: str = "") -> str:
    error_html = f"<p class='error'>{escape(error)}</p>" if error else ""
    return page_shell(
        "Project MedGenome Login",
        f"""
        <section class="login">
          <div class="login-art">
            <h1>Project MedGenome</h1>
            <p>Secure research operations for genomic datasets, sequencing workloads, and precision medicine studies.</p>
          </div>
          <div class="login-card">
            <div class="panel">
              <h2>Operations Login</h2>
              <p>Demo credentials: <strong>admin</strong> / <strong>admin</strong></p>
              {error_html}
              <form method="post" action="/login">
                <label>Username <input name="username" autocomplete="username" required></label>
                <label>Password <input name="password" type="password" autocomplete="current-password" required></label>
                <button class="primary" type="submit">Sign in</button>
              </form>
            </div>
          </div>
        </section>
        """,
    )


def dashboard_page(request: Request) -> str:
    summary = platform_summary()
    workload_rows = "".join(
        f"""
        <tr>
          <td>{escape(w.id)}</td>
          <td>{escape(w.study)}</td>
          <td>{escape(w.pipeline)}</td>
          <td><span class="status {escape(w.status)}">{escape(w.status)}</span></td>
          <td>{w.samples}</td>
          <td>{escape(w.region)}</td>
          <td>{w.compute_hours}</td>
        </tr>
        """
        for w in WORKLOADS
    )
    dataset_rows = "".join(
        f"""
        <tr>
          <td>{escape(d.id)}</td>
          <td>{escape(d.filename)}</td>
          <td>{escape(d.study)}</td>
          <td>{escape(d.file_type)}</td>
          <td>{escape(d.owner)}</td>
          <td>{format_bytes(d.size_bytes)}</td>
          <td>{escape(d.linked_workload)}</td>
        </tr>
        """
        for d in reversed(DATASET_REGISTRY)
    )
    return page_shell(
        "Project MedGenome Operations Portal",
        f"""
        <nav class="topbar">
          <div class="brand">
            <strong>MedGenome Ops</strong>
            <span>Signed in as admin</span>
          </div>
          <div class="nav">
            <a href="/docs">API Docs</a>
            <a href="/metrics">Metrics</a>
            <a href="/healthz">Health</a>
            <a class="primary" href="/logout">Logout</a>
          </div>
        </nav>
        <section class="hero">
          <div>
            <h1>Global Genomics Research Platform</h1>
            <p>Track sequencing uploads, active compute workloads, research cohorts, and operational health from one control plane.</p>
          </div>
        </section>
        <main>
          <section class="grid">
            <div class="metric"><span>Active Jobs</span><strong>{summary["active_jobs"]}</strong></div>
            <div class="metric"><span>Samples</span><strong>{summary["samples_processed"]}</strong></div>
            <div class="metric"><span>Uploaded Data</span><strong>{summary["dataset_size"]}</strong></div>
            <div class="metric"><span>Datasets</span><strong>{summary["dataset_count"]}</strong></div>
          </section>

          <section class="layout">
            <div class="panel">
              <h2>Upload Genomic Dataset</h2>
              <form method="post" action="/upload" enctype="multipart/form-data">
                <label>Study Name <input name="study" value="Synthetic Research Batch" required></label>
                <label>Owner / Institution <input name="owner" value="MedGenome Research Ops" required></label>
                <label>File Type
                  <select name="file_type">
                    <option>FASTQ</option>
                    <option>BAM</option>
                    <option>VCF</option>
                    <option>CSV Metadata</option>
                  </select>
                </label>
                <label>Sequencing File <input name="file" type="file" required></label>
                <button class="primary" type="submit">Upload and Register Dataset</button>
              </form>
            </div>
            <div class="panel">
              <h2>Dataset Registry</h2>
              <div class="table-wrap">
                <table>
                  <thead><tr><th>ID</th><th>File</th><th>Study</th><th>Type</th><th>Owner</th><th>Actual Size</th><th>Workload</th></tr></thead>
                  <tbody>{dataset_rows}</tbody>
                </table>
              </div>
            </div>
          </section>

          <section class="panel" style="margin-top:20px">
            <h2>Compute Workloads</h2>
            <div class="table-wrap">
              <table>
                <thead><tr><th>ID</th><th>Study</th><th>Pipeline</th><th>Status</th><th>Samples</th><th>Region</th><th>Compute Hours</th></tr></thead>
                <tbody>{workload_rows}</tbody>
              </table>
            </div>
          </section>
        </main>
        """,
    )


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    redirect = require_login(request)
    if redirect:
        return redirect
    return dashboard_page(request)


@app.get("/login", response_class=HTMLResponse)
def login_form():
    return login_page()


@app.post("/login")
def login(username: str = Form(...), password: str = Form(...)):
    if compare_digest(username, ADMIN_USERNAME) and compare_digest(password, ADMIN_PASSWORD):
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(SESSION_COOKIE, SESSION_VALUE, httponly=True, samesite="lax")
        return response
    return HTMLResponse(login_page("Invalid username or password."), status_code=401)


@app.get("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response


@app.post("/upload")
async def upload_dataset(
    request: Request,
    study: str = Form(...),
    owner: str = Form(...),
    file_type: str = Form(...),
    file: UploadFile = File(...),
):
    redirect = require_login(request)
    if redirect:
        return redirect

    size_bytes = 0
    while chunk := await file.read(1024 * 1024):
        size_bytes += len(chunk)

    workload = Workload(
        id=f"MG-{randint(2000, 9999)}",
        study=study,
        pipeline=choice(["WGS", "RNA-Seq", "Variant Calling", "GWAS", "Pharma Cohort"]),
        status="queued",
        samples=max(1, size_bytes // 8_000_000 or randint(12, 80)),
        region=choice(["us-east", "eu-west", "ap-south"]),
        compute_hours=round(max(0.25, size_bytes / 75_000_000), 2),
    )
    dataset = Dataset(
        id=f"DS-{uuid4().hex[:8].upper()}",
        filename=file.filename or "unnamed-sequencing-file",
        study=study,
        file_type=file_type,
        owner=owner,
        size_bytes=size_bytes,
        uploaded_at=datetime.now(timezone.utc).isoformat(),
        linked_workload=workload.id,
    )
    WORKLOADS.append(workload)
    DATASET_REGISTRY.append(dataset)
    UPLOADS.inc()
    UPLOADED_BYTES.inc(size_bytes)
    return RedirectResponse("/", status_code=303)


@app.get("/api/summary")
def summary():
    return platform_summary()


@app.get("/api/workloads")
def workloads():
    return WORKLOADS


@app.get("/api/datasets")
def datasets():
    return DATASET_REGISTRY


@app.post("/api/workloads", status_code=201)
def create_workload(workload: Workload):
    WORKLOADS.append(workload)
    if workload.status == "failed":
        FAILED_JOBS.inc()
    return workload


@app.post("/api/simulate")
def simulate():
    workload = Workload(
        id=f"MG-{randint(2000, 9999)}",
        study="Synthetic Research Batch",
        pipeline="Variant Calling",
        status="queued",
        samples=randint(50, 900),
        region="us-east",
        compute_hours=round(uniform(1, 40), 2),
    )
    WORKLOADS.append(workload)
    return JSONResponse({"created": workload.model_dump(), "summary": platform_summary()}, status_code=201)


@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": "medgenome-portal"}


@app.get("/readyz")
def readyz():
    return {"status": "ready"}


@app.get("/metrics")
def metrics():
    platform_summary()
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
