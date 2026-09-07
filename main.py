from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

app = FastAPI()

templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    # 新版語法：明確將 request 作為第一個參數傳入，或使用 request=request
    return templates.TemplateResponse(
        request=request, 
        name="index.html", 
        context={"title": "冷氣資料管理系統"}
    )