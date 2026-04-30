#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# ========== 第一步：核心补丁与编码设置 ==========
import httpx

def _normalize_header_value_fixed(value, encoding):
    final_encoding = encoding or "utf-8"
    if isinstance(value, str):
        return value.encode(final_encoding)
    elif isinstance(value, bytes):
        try:
            return value.decode(final_encoding).encode(final_encoding)
        except UnicodeDecodeError:
            return value
    else:
        return str(value).encode(final_encoding)

httpx._models._normalize_header_value = _normalize_header_value_fixed

import asyncio
import os
import sys
import json
import uuid
import datetime
from graphiti_core import Graphiti
from graphiti_core.llm_client.openai_client import OpenAIClient
# 保存原始的生成函数
original_generate_response = OpenAIClient.generate_response

async def patched_generate_response(self, *args, **kwargs):
    # 智能调整 max_tokens：提取边需要更大的 token 空间
    if 'max_tokens' in kwargs:
        # 如果请求的 tokens 超过 4096，限制为 4096（足够处理复杂边提取）
        if kwargs['max_tokens'] > 4096:
            kwargs['max_tokens'] = 4096
    else:
        kwargs['max_tokens'] = 2048

    # 调用原始函数
    return await original_generate_response(self, *args, **kwargs)

# 替换原函数
OpenAIClient.generate_response = patched_generate_response
# =================================================================
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
from graphiti_core.nodes import EpisodeType  

# 环境编码设置
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8')

# ========== 配置区域 ==========
VLLM_VISION_URL = "http://localhost:8000/v1"
VLLM_EMBED_URL = "http://localhost:8005/v1"
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "your_password"
DATA_FILE = "combined_data.json"
MAX_TEXT_LENGTH = 1000  # 限制文本长度

# ========== 辅助工具函数 ==========
def load_project_group_id():
    """加载或生成项目组 ID"""
    config_file = "project_config.json"
    if os.path.exists(config_file):
        with open(config_file, "r", encoding="utf-8") as f:
            return json.load(f).get("group_id")
    
    new_id = str(uuid.uuid4())
    project_info = {
        "group_id": new_id,
        "project_name": "滨湖复星人形机器人产业园项目",
        "created_at": str(datetime.date.today())
    }
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(project_info, f, indent=4, ensure_ascii=False)
    return new_id

def split_text(text, max_length):
    """将长文本分割成多个短文本"""
    if len(text) <= max_length:
        return [text]
    
    # 按句子分割
    sentences = text.split('。')
    chunks = []
    current_chunk = ""
    
    for sentence in sentences:
        if len(current_chunk) + len(sentence) + 1 <= max_length:
            current_chunk += sentence + "。"
        else:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = sentence + "。"
    
    if current_chunk:
        chunks.append(current_chunk)
    
    return chunks

# 新增：手动确保 Neo4j 索引和属性存在的函数
async def ensure_neo4j_schema(graphiti):
    driver = graphiti.driver
    async with driver.session() as session:
        # 1. 创建向量索引 (Qwen3-Embedding-0.6B 通常是 1536 维)
        await session.run("""
            CREATE VECTOR INDEX entity_name_index IF NOT EXISTS
            FOR (n:Entity) ON (n.name_embedding)
            OPTIONS {indexConfig: {
              `vector.dimensions`: 1536,
              `vector.similarity_function`: 'cosine'
            }}
        """)
        print("✅ 向量索引已检查/创建")

# 修改后的导入主函数
async def import_combined_data():
    group_id = load_project_group_id()
    print(f"🚀 正在处理项目组: {group_id}")
    
    # 重新填入你之前的配置，不要再用 ... 啦
    llm_config = LLMConfig(
        api_key="EMPTY",
        base_url=VLLM_VISION_URL,
        model="Qwen3-VL-8B-Instruct",
        small_model="Qwen3-VL-8B-Instruct",
        max_tokens=4096
    )
    
    graphiti = Graphiti(
        uri=NEO4J_URI,
        user=NEO4J_USER,
        password=NEO4J_PASSWORD,
        llm_client=OpenAIClient(config=llm_config),
        embedder=OpenAIEmbedder(
            config=OpenAIEmbedderConfig(
                api_key="EMPTY",
                base_url=VLLM_EMBED_URL,
                embedding_model="Qwen3-Embedding-0.6B",
            )
        ),
        cross_encoder=OpenAIRerankerClient(
            config=LLMConfig(
                api_key="EMPTY",
                base_url=VLLM_VISION_URL,
                model="Qwen3-VL-8B-Instruct",
                max_tokens=4096
            )
        )
    )

    # 1. 基础索引建立
    await graphiti.build_indices_and_constraints()
    # 2. 强力补丁：手动补全向量索引
    await ensure_neo4j_schema(graphiti)

    # 查看 LLM 客户端的配置
    if hasattr(graphiti.llm_client, 'config'):
        cfg = graphiti.llm_client.config
        print(f"LLM Model: {cfg.model}")
        print(f"LLM Max Tokens: {cfg.max_tokens}")
        print(f"LLM 全量配置: {cfg}")

    if not os.path.exists(DATA_FILE):
        print(f"错误：找不到 {DATA_FILE}")
        return

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 用于记录上一个板块的 UUID，实现导览链条
    last_episode_uuid = None

    for item in data:
        plate_name = item['name']
        sentences = item['sentences']
        location = item['location']
        
        print("\n" + "="*50)
        print(f"当前板块: {plate_name}")
        print(f"位置: {location}")
        print(f"句子数量: {len(sentences)}")
        print("="*50)
        
        combined_text = ' '.join(sentences)
        text_chunks = split_text(combined_text, MAX_TEXT_LENGTH)
        
        for i, chunk in enumerate(text_chunks):
            # 写入并获取当前 episode 对象
            print(f"正在写入 {plate_name}_{i+1} 到数据库...")
            result = await graphiti.add_episode(
                name=f"{plate_name}_{i+1}",
                episode_body=chunk,
                source=EpisodeType.text,
                source_description=json.dumps({
                    "plate_name": plate_name,
                    "location": location,
                    "group_id": group_id
                }, ensure_ascii=False),
                reference_time=datetime.datetime.now(datetime.timezone.utc)
            )
            
            # AddEpisodeResults 包含 episode 属性，uuid 在 episode 对象中
            current_uuid = result.episode.uuid
            print(f"✅ {plate_name} 第 {i+1} 块已入库, UUID: {current_uuid}")

            # 【导览逻辑】手动建立前后板块的顺序连接
            if last_episode_uuid:
                async with graphiti.driver.session() as session:
                    await session.run("""
                        MATCH (prev:Episodic {uuid: $prev_uuid})
                        MATCH (curr:Episodic {uuid: $curr_uuid})
                        MERGE (prev)-[:NEXT_GUIDE]->(curr)
                    """, prev_uuid=last_episode_uuid, curr_uuid=current_uuid)
                print(f"🔗 已建立导览链条: 上一个节点 -> {plate_name}_{i+1}")

            last_episode_uuid = current_uuid

    print("\n所有板块处理完毕且导览链条已构建。")

if __name__ == "__main__":
    asyncio.run(import_combined_data())