
import os
from typing import Dict, Any
from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import JSONResponse
from rabbitbot.memory.agent_memory import AgentMemory
from rabbitbot.provider import get_llm
import ast
import tempfile
from typing import List
from graphiti_core.nodes import EntityNode
from neo4j import GraphDatabase

app = FastAPI()

llm_cfg = get_llm(None, None)
neo4j_url = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
neo4j_user = os.getenv('NEO4J_USER', 'neo4j')
neo4j_password = os.getenv('NEO4J_PASSWORD', 'your_password')
embd_model = os.getenv('GRAPHITI_EMBD_MODEL', 'Qwen3-Embedding-0.6B')
embd_model_url = os.getenv('GRAPHITI_EMBD_MODEL_URL', 'http://localhost:8005/v1')
rerank_model = os.getenv('GRAPHITI_RERANK_MODEL', llm_cfg['model'])
rerank_model_url = os.getenv('GRAPHITI_RERANK_MODEL_URL', 'http://localhost:8000/v1')

print(embd_model)
print(embd_model_url)
print(rerank_model)
print(rerank_model_url)

agent = AgentMemory(
    llm_cfg=llm_cfg,
    neo4j_url=neo4j_url,
    neo4j_user=neo4j_user,
    neo4j_password=neo4j_password,
    embd_model=embd_model,
    embd_model_url=embd_model_url,
    rerank_model=rerank_model,
    rerank_model_url=rerank_model_url,
)
def create_empty_node_response(task: str):
    return EntityNode(
                uuid='114514',
                name='异常结点',
                group_id="",
                summary='不好意思，我检索不到您想要找的物品',
                attributes={
                    'location': None,
                    'image_path': None,
                    'description': '不好意思，我检索不到您想要找的物品',
                },
            )

@app.post("/update")
async def update_api(task: str = Form(...)):
    try:
        print(f"Get data")
        print(task)
        entities = ast.literal_eval(task)
        print(entities)
        await agent.init_graphiti_if_not()
        await agent.update(entities)

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.post("/get_all_names")
async def get_all_nodes_name(task: str = Form(...)):
    try:
        driver = GraphDatabase.driver(neo4j_url, auth=(neo4j_user, neo4j_password))
        with driver.session() as session:
            result = session.run("MATCH (n) RETURN n")
            nodes = []
            for record in result:
                nodes.append(record["n"])
        node_name=[]
        for node in nodes:
            if node.get("name")!="房间":
               node_name.append(node.get("name"))
        print(node_name)
        driver.close()
        return node_name
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.post("/get_group_names")
async def get_group_nodes_name(task: str = Form(...)):
    try:
        driver = GraphDatabase.driver(neo4j_url, auth=(neo4j_user, neo4j_password))
        with driver.session() as session:
            result = session.run(f"MATCH (n) WHERE n.group_id='{task}' RETURN n")
            nodes = []
            for record in result:
                nodes.append(record["n"])
        node_name=[]
        for node in nodes:
            if node.get("name")!="房间":
               node_name.append(node.get("name"))
        print(node_name)
        driver.close()
        return node_name
    except Exception as e:
        print(str(e))
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.post("/get_group_summary")
async def get_group_nodes_name(task: str = Form(...)):
    try:
        driver = GraphDatabase.driver(neo4j_url, auth=(neo4j_user, neo4j_password))
        with driver.session() as session:
            result = session.run(f"MATCH (n) WHERE n.group_id='{task}' RETURN n")
            nodes = []
            for record in result:
                nodes.append(record["n"])

        # 创建字典存储 name:summary 映射
        node_dict = {}
        for node in nodes:
            name = node.get("name")
            if name and name != "房间":
                node_dict[name] = node.get("summary", "")

        print(node_dict)
        driver.close()
        return node_dict

    except Exception as e:
        print(str(e))
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.post("/query")
async def query_api(task: str = Form(...)):
    try:
        await agent.init_graphiti_if_not()
        print(f"Get data")
        print(task)
        task = ast.literal_eval(task)
        query, group_name = task['query'], task['group_name']
        if query == "异常结点":
            return create_empty_node_response(
                    query
                )
        task_embedding = await agent.create_embedding(query)
        print(f"Query nodes")
        nodes = await agent.query(query,group_name=group_name)
        print(nodes)
        location = None
        description =None
        similarity_threshold=0.35
        best_similarity=0
        if len(nodes) > 0:
            for node in nodes:
                # 为节点名称生成 embedding
                node_embedding = await agent.create_embedding(node.name)
                # 计算相似度
                similarity = agent.cosine_similarity(task_embedding, node_embedding)

                print(f"节点: {node.name}, 相似度: {similarity:.4f}")

                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match = node
            if best_similarity < similarity_threshold:
                return create_empty_node_response(
                    query
                )
            else:
                return best_match
        return nodes[0]

        #return JSONResponse(content={"name":str(name), "location": str(location),"summary":str(summary),"description":str(description)})

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)
