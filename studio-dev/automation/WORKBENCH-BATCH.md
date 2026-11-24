# 批量状态与原任务观察

workbench_batch.py 读取本机本次真实的空间绑定文件；使用 --help 查看当前参数。
status 为只读状态核对。supplier-add --execute 会执行货源采集，必须具备当前任务授权并保持90秒串行间隔。
observe --execute --job 原任务ID 仅接续当前账号的真实原刊登观察；未知状态先对账，不新建发布任务。

supplier_image_review.py 只下载已观察结果中的公开商品图，保留SHA；下载成功不代表同款或图片权利通过。
native_supplier_observation.mjs 只观察正式队列已绑定的当前货源页；页面、货源ID和用户验证状态不符时停止。
native_sellersprite_research.mjs 保留原生完整导出与SHA；部分可见行不能代替完整研究结果。
ziniao_inventory_observe.py 只核对当前真实父子SKU全集，区分发布中、受理、在售和缺失信息。

本包不附历史 spaces.json、原任务号、真实商品记录或原店铺授权。按当前机器已确认的账号和店铺重新绑定后再执行。
