"""Reject unsupported operations before any scientific task can be arranged."""
import re
from .path_rules import text_without_paths

def unsupported_request(text):
    value=text_without_paths(text).casefold()
    # Match a file/data object, not image-processing phrases such as remove stripes.
    pattern=r'\b(?:delete|erase|remove)\s+(?:(?:all|my|the|these|those|original|source|input|raw)\s+){0,6}(?:pictures?|images?|files?|folders?|datasets?|checkpoints?|originals?|data)\b'
    for match in re.finditer(pattern,value):
        if not re.search(r"(?:do\s+not|don't|never|must\s+not|without)\s*$",value[max(0,match.start()-30):match.start()]):return 'file_deletion'
    for match in re.finditer(r'删除\s*(?:(?:所有|全部|这些|我的|原始|源|输入|已选)\s*)*(?:图片|图像|文件|文件夹|数据集|数据|原图|checkpoint)',value):
        if not re.search(r'(?:不要|不能|别|不允许)\s*$',value[max(0,match.start()-8):match.start()]):return 'file_deletion'
    automatic=bool(re.search(r'\bauto(?:matic(?:ally)?)?\b|自动',value))
    manual=bool(re.search(r'\b(?:trials?|sweeps?|jitter|candidates?)\b|抖动|试重建|候选|我(?:自己)?挑',value))
    if automatic and not manual:
        target=r'\b(?:find|optimi[sz]e|estimate|search\s+for|score)(?:\s+(?:and|the|best|optimal|laminography|lamino|tilt|rotation|automatically)){0,6}\s+angles?\b'
        reverse=r'\b(?:laminography\s+|lamino\s+|tilt\s+)?angle\s+(?:search|estimation|optimization|scoring)\b'
        chinese=r'(?:寻找|查找|优化|估计|搜索|找|评分)\s*(?:最佳|最优|合适|的|一下|出|一个|这个|该|\s)*(?:lamino(?:graphy)?\s*angle|倾斜角|层析角|角度)'
        if re.search(target,value) or re.search(reverse,value) or re.search(chinese,value):return 'automatic_angle'
    return None

MESSAGES={
 'file_deletion':('MomoBot cannot delete source files or datasets. You can delete a saved conversation with Delete task; generated results and source data are kept.','MomoBot 不支持删除原始文件或数据集。删除聊天任务请使用 Delete task；原始数据和计算结果会保留。'),
 'automatic_angle':('Automatic laminography angle scoring is not implemented. I can generate angle trial reconstructions for you to compare and choose.','目前不支持自动评分查找 laminography 倾斜角。我可以生成一组倾斜角试重建图片，由你比较并选择。')}
