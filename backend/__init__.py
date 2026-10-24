"""Fitness Coach 2.0 后端服务层（TASKBOOK_2.0 B4）。

薄封装：路由只做参数提取与错误映射，业务全部委托 coach/ 域模块；
不移动、不重写 coach/ 现有代码。CLI（main.py）保留为调试入口。
"""
