"""FastAPI application for Mastodon Post Generator API."""
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List
import os
import time
from dotenv import load_dotenv
from database import (
    init_database, create_post, get_post, get_posts,
    update_post, delete_post, log_api_request, get_stats
)
from rag_database import init_rag_database, get_embedding_stats
from rag_retrieval import retrieve_context, embed_notion_content
from hybrid_search import hybrid_search
from embeddings import generate_embedding

# Load environment variables
load_dotenv()

# Initialize databases on startup
init_database()
init_rag_database()

app = FastAPI(
    title="Mastodon Post Generator API",
    description="API for generating Mastodon posts from Notion content with SQLite database",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)


class HealthResponse(BaseModel):
    status: str
    message: str


class PostRequest(BaseModel):
    content: str
    tags: Optional[List[str]] = None
    notion_page_id: Optional[str] = None
    status: Optional[str] = "draft"


class PostUpdateRequest(BaseModel):
    content: Optional[str] = None
    tags: Optional[List[str]] = None
    status: Optional[str] = None
    mastodon_post_id: Optional[str] = None


@app.get("/", response_model=HealthResponse)
async def root():
    """Root endpoint."""
    return HealthResponse(
        status="ok",
        message="Mastodon Post Generator API is running"
    )


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        message="API is operational"
    )


@app.get("/api/info")
async def api_info():
    """Get API information."""
    return {
        "name": "Mastodon Post Generator API",
        "version": "1.0.0",
        "docs": "/docs",
        "redoc": "/redoc",
        "openapi": "/openapi.json",
        "database": "SQLite"
    }


@app.post("/api/posts", status_code=status.HTTP_201_CREATED)
async def create_post_endpoint(request: PostRequest):
    """Create a new post in the database."""
    start_time = time.time()
    try:
        post_id = create_post(
            content=request.content,
            tags=request.tags,
            notion_page_id=request.notion_page_id,
            status=request.status or "draft"
        )
        response_time = (time.time() - start_time) * 1000
        log_api_request("/api/posts", "POST", 201, response_time)
        
        return {
            "id": post_id,
            "message": "Post created successfully",
            "content": request.content,
            "tags": request.tags or [],
            "status": request.status or "draft"
        }
    except Exception as e:
        response_time = (time.time() - start_time) * 1000
        log_api_request("/api/posts", "POST", 500, response_time)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/posts/{post_id}")
async def get_post_endpoint(post_id: int):
    """Get a post by ID."""
    start_time = time.time()
    post = get_post(post_id)
    response_time = (time.time() - start_time) * 1000
    
    if not post:
        log_api_request(f"/api/posts/{post_id}", "GET", 404, response_time)
        raise HTTPException(status_code=404, detail="Post not found")
    
    log_api_request(f"/api/posts/{post_id}", "GET", 200, response_time)
    return post


@app.get("/api/posts")
async def list_posts(limit: int = 10, offset: int = 0, status_filter: Optional[str] = None):
    """Get a list of posts."""
    start_time = time.time()
    posts = get_posts(limit=limit, offset=offset, status=status_filter)
    response_time = (time.time() - start_time) * 1000
    log_api_request("/api/posts", "GET", 200, response_time)
    return {
        "posts": posts,
        "limit": limit,
        "offset": offset,
        "count": len(posts)
    }


@app.put("/api/posts/{post_id}")
async def update_post_endpoint(post_id: int, request: PostUpdateRequest):
    """Update a post."""
    start_time = time.time()
    success = update_post(
        post_id=post_id,
        content=request.content,
        tags=request.tags,
        status=request.status,
        mastodon_post_id=request.mastodon_post_id
    )
    response_time = (time.time() - start_time) * 1000
    
    if not success:
        log_api_request(f"/api/posts/{post_id}", "PUT", 404, response_time)
        raise HTTPException(status_code=404, detail="Post not found")
    
    log_api_request(f"/api/posts/{post_id}", "PUT", 200, response_time)
    return {"message": "Post updated successfully", "id": post_id}


@app.delete("/api/posts/{post_id}")
async def delete_post_endpoint(post_id: int):
    """Delete a post."""
    start_time = time.time()
    success = delete_post(post_id)
    response_time = (time.time() - start_time) * 1000
    
    if not success:
        log_api_request(f"/api/posts/{post_id}", "DELETE", 404, response_time)
        raise HTTPException(status_code=404, detail="Post not found")
    
    log_api_request(f"/api/posts/{post_id}", "DELETE", 200, response_time)
    return {"message": "Post deleted successfully", "id": post_id}


@app.get("/api/stats")
async def get_stats_endpoint():
    """Get database statistics."""
    start_time = time.time()
    stats = get_stats()
    response_time = (time.time() - start_time) * 1000
    log_api_request("/api/stats", "GET", 200, response_time)
    return stats


class RAGSearchRequest(BaseModel):
    query: str
    top_k: Optional[int] = 10
    keyword_weight: Optional[float] = 0.5
    semantic_weight: Optional[float] = 0.5


class RAGEmbedRequest(BaseModel):
    force_reembed: Optional[bool] = False


@app.post("/api/rag/embed")
async def embed_notion_endpoint(request: RAGEmbedRequest):
    """Manually trigger embedding of Notion content."""
    start_time = time.time()
    try:
        chunks_embedded = embed_notion_content(force_reembed=request.force_reembed)
        response_time = (time.time() - start_time) * 1000
        log_api_request("/api/rag/embed", "POST", 200, response_time)
        return {
            "message": "Embedding completed",
            "chunks_embedded": chunks_embedded
        }
    except Exception as e:
        response_time = (time.time() - start_time) * 1000
        log_api_request("/api/rag/embed", "POST", 500, response_time)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/rag/search")
async def rag_search_endpoint(request: RAGSearchRequest):
    """Perform hybrid search with RAG."""
    start_time = time.time()
    try:
        query_embedding = generate_embedding(request.query)
        from rag_database import get_rag_connection
        
        with get_rag_connection() as conn:
            results = hybrid_search(
                conn,
                request.query,
                query_embedding,
                keyword_weight=request.keyword_weight,
                semantic_weight=request.semantic_weight,
                top_k=request.top_k
            )
        
        response_time = (time.time() - start_time) * 1000
        log_api_request("/api/rag/search", "POST", 200, response_time)
        return {
            "query": request.query,
            "results": results,
            "count": len(results)
        }
    except Exception as e:
        response_time = (time.time() - start_time) * 1000
        log_api_request("/api/rag/search", "POST", 500, response_time)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/rag/stats")
async def get_rag_stats_endpoint():
    """Get RAG embedding statistics."""
    start_time = time.time()
    try:
        stats = get_embedding_stats()
        response_time = (time.time() - start_time) * 1000
        log_api_request("/api/rag/stats", "GET", 200, response_time)
        return stats
    except Exception as e:
        response_time = (time.time() - start_time) * 1000
        log_api_request("/api/rag/stats", "GET", 500, response_time)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/posts/with-rag")
async def create_post_with_rag_endpoint(request: PostRequest):
    """Create a post using RAG retrieval."""
    start_time = time.time()
    try:
        # Use post content as the query for RAG
        rag_context, results = retrieve_context(request.content, top_k=10)
        
        # Generate post using RAG context
        from llm import generate_post_with_rag
        post_content = generate_post_with_rag(rag_context, topic=request.content)
        
        # Save to database
        post_id = create_post(
            content=post_content,
            tags=request.tags,
            status="draft"
        )
        
        response_time = (time.time() - start_time) * 1000
        log_api_request("/api/posts/with-rag", "POST", 201, response_time)
        
        return {
            "id": post_id,
            "message": "Post created with RAG",
            "content": post_content,
            "tags": request.tags or [],
            "rag_results_count": len(results)
        }
    except Exception as e:
        response_time = (time.time() - start_time) * 1000
        log_api_request("/api/posts/with-rag", "POST", 500, response_time)
        raise HTTPException(status_code=500, detail=str(e))


# Automation endpoints
try:
    from automation import get_automation_listener
    import asyncio
    from fastapi import BackgroundTasks

    @app.on_event("startup")
    async def startup_event():
        """Start automation listeners on API startup (if enabled)."""
        if os.getenv("AUTO_START_LISTENERS", "false").lower() == "true":
            listener = get_automation_listener()
            # Start in background
            asyncio.create_task(listener.start())

    @app.post("/api/automation/start")
    async def start_automation_endpoint(background_tasks: BackgroundTasks):
        """Start the automation listeners."""
        try:
            listener = get_automation_listener()
            if not listener.running:
                background_tasks.add_task(listener.start)
                return {"message": "Automation listeners started", "status": "running"}
            else:
                return {"message": "Automation listeners already running", "status": "running"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/automation/stop")
    async def stop_automation_endpoint():
        """Stop the automation listeners."""
        try:
            listener = get_automation_listener()
            listener.stop()
            return {"message": "Automation listeners stopped", "status": "stopped"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/automation/status")
    async def get_automation_status():
        """Get automation listeners status."""
        try:
            listener = get_automation_listener()
            return {
                "running": listener.running,
                "last_notion_check": len(listener.last_notion_check),
                "processed_notifications": len(listener.processed_notifications)
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
except ImportError:
    # Automation module not available
    pass


if __name__ == "__main__":
    import uvicorn
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
