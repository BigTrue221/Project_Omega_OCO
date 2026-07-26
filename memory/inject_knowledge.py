# -*- coding: utf-8 -*-
"""
Knowledge Injection Script
将写作领域核心知识注入到 OCO L3 长期记忆 (ChromaDB) 中。
"""

import asyncio
from AI_Ori.Project_Omega_OCO.memory.vector_store import OCO_VectorStore

async def inject_writing_knowledge():
    store = OCO_VectorStore()
    
    # 写作领域核心知识库
    knowledge_data = [
        {
            "content": "【小说大纲构建】大纲是故事的骨架。核心应包含：1. 故事核心 (Logline) - 一句话概括冲突与看点；2. 三幕结构 - 开端(建立世界观/引入冲突)、中段(冲突升级/反转)、结尾(解决冲突/给出结局)；3. 关键情节节点 - 确保每个节点都有推动作用。",
            "metadata": {"category": "outline", "importance": "high"}
        },
        {
            "content": "【人物设定 (Character Arc)】人物应具备：1. 核心欲望 (Want) - 表面目标；2. 核心需求 (Need) - 潜意识里的缺失；3. 矛盾点 (Conflict) - 欲望与需求的冲突。人物的成长弧线应在故事高潮处完成转变。",
            "metadata": {"category": "character", "importance": "high"}
        },
        {
            "content": "【戏剧冲突 (Conflict)】冲突是故事的发动机。分为：1. 内部冲突 (人物内心的挣扎)；2. 人际冲突 (人物与人物的对立)；3. 环境冲突 (人物与世界的对抗)。高明的冲突应是‘不可调和’且‘具有高代价’的。",
            "metadata": {"category": "conflict", "importance": "high"}
        },
        {
            "content": "【叙事节奏 (Pacing)】节奏如同钢琴曲，需有轻重缓急。1. 紧凑期：通过连续的冲突和反转推动情节；2. 缓和期：通过细节描写和人物互动深化情感。避免长时间的平铺直叙或无休止的高潮。",
            "metadata": {"category": "pacing", "importance": "medium"}
        },
        {
            "content": "【钩子 (Hook) 机制】在每个章节末尾设置‘钩子’，通过留下悬念或未解决的矛盾，强迫读者进入下一章。常见的钩子包括：突然的危机、揭露关键秘密、人物的意外决定。",
            "metadata": {"category": "technique", "importance": "medium"}
        },
        {
            "content": "【网文黄金三章】1. 第一章：快速建立主角人设，抛出核心矛盾，给读者一个‘必须看下去’的理由；2. 第二章：深化冲突，展现主角的独特能力或困境；3. 第三章：确立长期目标，完成第一个小高潮。",
            "metadata": {"category": "web_novel", "importance": "high"}
        }
    ]
    
    print(f"--- Starting Knowledge Injection ({len(knowledge_data)} entries) ---")
    for item in knowledge_data:
        await store.upsert(item["content"], item["metadata"])
    
    print("✅ Knowledge injection completed successfully.")

if __name__ == "__main__":
    asyncio.run(inject_writing_knowledge())