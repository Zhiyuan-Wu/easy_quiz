// 前端配置文件
// 所有可配置的参数都集中在这里，方便修改

const APP_CONFIG = {
    // 试卷解析进度条配置
    parsingProgress: {
        interval: 200,        // 进度更新间隔（毫秒）
        increment: 0.175,         // 每次增加的百分比
        maxProgress: 99       // 最大进度值（达到此值后停止）
    },
    
    // 图片显示配置
    imageDisplay: {
        defaultScale: 0.8     // 默认缩放比例（0-1之间，1为原始大小）
    },
    
    // 其他前端配置可以在这里添加
    // ...
};

