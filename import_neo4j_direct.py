#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""直接使用 Neo4j 驱动导入导览数据。

该脚本不依赖 LLM 抽取服务；如果本机 Embedding 服务可用，会额外写入
Graphiti 节点搜索使用的 name_embedding。
"""

import os
import json
import uuid
import urllib.error
import urllib.request
from pathlib import Path
from neo4j import GraphDatabase

# 配置
NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'neo4j_pass')
SCRIPT_DIR = Path(__file__).resolve().parent
DATA_FILE = Path(os.getenv('DATA_FILE', SCRIPT_DIR / "combined_data.json"))
ENTITY_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "rabbitbot:neo4j-direct-import")
EMBEDDING_URL = os.getenv('GRAPHITI_EMBD_MODEL_URL', 'http://localhost:8005/v1').rstrip('/') + '/embeddings'
EMBEDDING_MODEL = os.getenv('GRAPHITI_EMBD_MODEL', 'Qwen3-Embedding-0.6B')
GENERATE_NAME_EMBEDDINGS = os.getenv('GENERATE_NAME_EMBEDDINGS', '1') == '1'


def stable_entity_uuid(entity_name):
    """按展点名称生成稳定 UUID，避免重复运行脚本时重复导入同一展点。"""
    return str(uuid.uuid5(ENTITY_NAMESPACE, entity_name))


def create_name_embedding(text):
    """调用 OpenAI 兼容 Embedding 服务生成 Graphiti 节点搜索使用的 name_embedding。"""
    if not GENERATE_NAME_EMBEDDINGS:
        return None

    payload = json.dumps({
        "model": EMBEDDING_MODEL,
        "input": text.replace('\n', ' ').strip(),
    }).encode("utf-8")
    request = urllib.request.Request(
        EMBEDDING_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
            return body["data"][0]["embedding"]
    except (urllib.error.URLError, TimeoutError, KeyError, IndexError, json.JSONDecodeError) as exc:
        print(f"⚠️ 生成 name_embedding 失败，将继续导入但语义检索可能受限: {exc}")
        return None


def ensure_vector_index(session, dimensions):
    """确保 Neo4j 中存在 Graphiti 搜索 name_embedding 所需的向量索引。"""
    if not dimensions:
        return
    dimensions = int(dimensions)
    session.run(f"""
        CREATE VECTOR INDEX entity_name_index IF NOT EXISTS
        FOR (n:Entity) ON (n.name_embedding)
        OPTIONS {{indexConfig: {{
          `vector.dimensions`: {dimensions},
          `vector.similarity_function`: 'cosine'
        }}}}
    """)


def location_to_navigation_point(location_list):
    """将第一个导航点转换为当前 workflow 使用的 6 维导航位姿。"""
    if not location_list:
        return (0, 0, 0, 0, 0, 1)
    loc = location_list[0]
    return (
        loc.get('x', 0),
        loc.get('y', 0),
        loc.get('ox', 0),
        loc.get('oy', 0),
        loc.get('oz', 0),
        loc.get('ow', 0)
    )


def location_to_pose(location_list):
    """保留第一个导航点的完整 7 维位姿，便于后续切换到含 z 的导航接口。"""
    if not location_list:
        return (0, 0, 0, 0, 0, 0, 1)
    loc = location_list[0]
    return (
        loc.get('x', 0),
        loc.get('y', 0),
        loc.get('z', 0),
        loc.get('ox', 0),
        loc.get('oy', 0),
        loc.get('oz', 0),
        loc.get('ow', 0)
    )


def location_mode(location_list):
    """读取第一个导航点的模式，缺省时保持原始数据约定的 mode=1。"""
    if not location_list:
        return 1
    return location_list[0].get('mode', 1)


def import_data():
    """直接导入数据到 Neo4j"""
    
    # 读取数据
    if not DATA_FILE.exists():
        print(f"❌ 找不到数据文件: {DATA_FILE}")
        return

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"📂 读取到 {len(data)} 个展点")
    
    # 连接 Neo4j
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    with driver.session() as session:
        # 1. 创建房间节点
        room_uuid = "efe754d7-cb90-430c-9143-5c51baa6755"
        session.run("""
            MERGE (r:Entity {uuid: $room_uuid})
            SET r.name = '房间',
                r.group_id = '',
                r.summary = '房间节点',
                r.entity_type = 'Room',
                r.created_at = coalesce(r.created_at, datetime()),
                r.updated_at = datetime()
        """, room_uuid=room_uuid)
        print(f"✅ 房间节点已创建")

        # 清理本次数据集中展点之间的旧导览顺序，避免 JSON 顺序变化后留下过期链路。
        entity_uuids = [stable_entity_uuid(item['name']) for item in data]
        session.run("""
            MATCH (prev:Entity)-[rel:下一站]->(curr:Entity)
            WHERE prev.uuid IN $entity_uuids AND curr.uuid IN $entity_uuids
            DELETE rel
        """, entity_uuids=entity_uuids)
        
        # 2. 导入每个展点
        last_uuid = None
        vector_index_ready = False
        
        for i, item in enumerate(data, 1):
            plate_name = item['name']
            sentences = item['sentences']
            location = item['location']
            
            description = ''.join(sentences)
            summary = sentences[0] if sentences else plate_name
            navigation_point = location_to_navigation_point(location)
            pose = location_to_pose(location)
            mode = location_mode(location)
            locations_json = json.dumps(location, ensure_ascii=False)
            
            entity_uuid = stable_entity_uuid(plate_name)
            name_embedding = create_name_embedding(plate_name)
            if name_embedding and not vector_index_ready:
                ensure_vector_index(session, len(name_embedding))
                vector_index_ready = True
            
            print(f"\n[{i}/{len(data)}] 正在导入: {plate_name}")
            print(f"   UUID: {entity_uuid}")
            print(f"   位置: {navigation_point}")
            print(f"   摘要: {summary[:40]}...")
            
            # 创建实体节点
            session.run("""
                MERGE (e:Entity {uuid: $uuid})
                SET e.name = $name,
                    e.group_id = $group_id,
                    e.summary = $summary,
                    e.entity_type = 'Object',
                    e.created_at = coalesce(e.created_at, datetime()),
                    e.updated_at = datetime(),
                    e.name_embedding = $name_embedding,
                    e.location = $location,
                    e.pose = $pose,
                    e.locations = $locations,
                    e.mode = $mode,
                    e.description = $description
            """, 
                uuid=entity_uuid,
                name=plate_name,
                group_id="展点",
                summary=summary,
                name_embedding=name_embedding,
                location=str(navigation_point),
                pose=str(pose),
                locations=locations_json,
                mode=mode,
                description=description[:5000]  # 截断过长的描述
            )
            
            # 建立与房间的关系
            session.run("""
                MATCH (e:Entity {uuid: $entity_uuid})
                MATCH (r:Entity {uuid: $room_uuid})
                MERGE (e)-[rel:属于]->(r)
                SET rel.fact = $fact,
                    rel.created_at = coalesce(rel.created_at, datetime())
            """,
                entity_uuid=entity_uuid,
                room_uuid=room_uuid,
                fact=f"{plate_name}属于房间"
            )
            
            # 建立导览链条（如果存在上一个节点）
            if last_uuid:
                session.run("""
                    MATCH (prev:Entity {uuid: $prev_uuid})
                    MATCH (curr:Entity {uuid: $curr_uuid})
                    MERGE (prev)-[rel:下一站]->(curr)
                    SET rel.created_at = coalesce(rel.created_at, datetime())
                """,
                    prev_uuid=last_uuid,
                    curr_uuid=entity_uuid
                )
                print(f"   🔗 导览链条已建立")
            
            last_uuid = entity_uuid
            print(f"   ✅ 导入完成")
    
    driver.close()
    
    print("\n" + "=" * 50)
    print("✅ 所有展点导入完成！")
    print(f"   分组名称: 展点")
    print(f"   展点数量: {len(data)}")
    print("=" * 50)
    
    # 验证导入结果
    print("\n📊 验证导入结果:")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session() as session:
        result = session.run("MATCH (e:Entity) WHERE e.name <> '房间' RETURN e.name as name, e.summary as summary")
        print("-" * 50)
        for record in result:
            print(f"  ✅ {record['name']}: {record['summary'][:30]}...")
    driver.close()


if __name__ == "__main__":
    try:
        import_data()
    except Exception as e:
        print(f"\n❌ 导入失败: {e}")
        import traceback
        traceback.print_exc()
