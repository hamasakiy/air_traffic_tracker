from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, HTMLResponse
from src.app import lambda_handler

app = FastAPI()


def build_event(request: Request, body_text: str = "") -> dict:
    query_params = dict(request.query_params)
    headers = {k: v for k, v in request.headers.items()}

    return {
        "version": "2.0",
        "routeKey": "$default",
        "rawPath": request.url.path,
        "rawQueryString": request.url.query,
        "headers": headers,
        "queryStringParameters": query_params if query_params else None,
        "requestContext": {
            "http": {
                "method": request.method,
                "path": request.url.path,
            }
        },
        "body": body_text,
        "isBase64Encoded": False,
    }


@app.api_route("/{path:path}", methods=["GET", "OPTIONS"])
async def proxy(path: str, request: Request):
    event = build_event(request)
    result = lambda_handler(event, None)

    status_code = result.get("statusCode", 200)
    headers = result.get("headers", {})
    body = result.get("body", "")

    content_type = headers.get("Content-Type", headers.get("content-type", ""))

    if "application/json" in content_type:
        import json
        return JSONResponse(
            content=json.loads(body) if body else None,
            status_code=status_code,
            headers=headers,
        )

    return HTMLResponse(
        content=body,
        status_code=status_code,
        headers=headers,
    )