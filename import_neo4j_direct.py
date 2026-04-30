#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""直接使用 Neo4j 驱动导入数据，不依赖 LLM 服务"""

import os
import json
import uuid
from neo4j import GraphDatabase

# 配置
NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'your_password')
DATA_FILE = "combined_data.json"


def location_to_tuple(location_list):
    """将 location 列表转换为元组格式"""
    if not location_list:
        return (0, 0, 0, 0, 0, 0)
    loc = location_list[0]
    return (
        loc.get('x', 0),
        loc.get('y', 0),
        loc.get('ox', 0),
        loc.get('oy', 0),
        loc.get('oz', 0),
        loc.get('ow', 0)
    )


def import_data():
    """直接导入数据到 Neo4j"""
    
    # 读取数据
    if not os.path.exists(DATA_FILE):
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
                r.created_at = datetime()
        """, room_uuid=room_uuid)
        print(f"✅ 房间节点已创建")
        
        # 2. 导入每个展点
        last_uuid = None
        
        for i, item in enumerate(data, 1):
            plate_name = item['name']
            sentences = item['sentences']
            location = item['location']
            
            description = ''.join(sentences)
            summary = sentences[0] if sentences else plate_name
            location_tuple = location_to_tuple(location)
            
            entity_uuid = str(uuid.uuid4())
            
            print(f"\n[{i}/{len(data)}] 正在导入: {plate_name}")
            print(f"   UUID: {entity_uuid}")
            print(f"   位置: {location_tuple}")
            print(f"   摘要: {summary[:40]}...")
            
            # 创建实体节点
            session.run("""
                MERGE (e:Entity {uuid: $uuid})
                SET e.name = $name,
                    e.group_id = $group_id,
                    e.summary = $summary,
                    e.entity_type = 'Object',
                    e.created_at = datetime(),
                    e.location = $location,
                    e.description = $description
            """, 
                uuid=entity_uuid,
                name=plate_name,
                group_id="展点",
                summary=summary,
                location=str(location_tuple),
                description=description[:5000]  # 截断过长的描述
            )
            
            # 建立与房间的关系
            session.run("""
                MATCH (e:Entity {uuid: $entity_uuid})
                MATCH (r:Entity {uuid: $room_uuid})
                MERGE (e)-[rel:属于 {created_at: datetime()}]->(r)
                SET rel.fact = $fact
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
                    SET rel.created_at = datetime()
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
