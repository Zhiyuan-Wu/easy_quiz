// 前端配置文件
// 所有可配置的参数都集中在这里，方便修改

window.APP_CONFIG = {
    // 试卷解析进度条配置
    parsingProgress: {
        interval: 200,           // 进度更新间隔（毫秒）
        increment: 0.175,        // 每次增加的百分比
        maxProgress: 99          // 最大进度值（达到此值后停止）
    },

    // 图片显示配置
    imageDisplay: {
        defaultScale: 0.8        // 默认缩放比例（0-1之间，1为原始大小）
    },

    // 布局和响应式配置
    layout: {
        mobileBreakpoint: 900,   // 视口宽度小于该值时视为移动端
        compactBreakpoint: 720   // 更窄视口下的紧凑布局断点
    },

    // 题目内容展示配置
    content: {
        manageListPageSize: 10,          // 题目管理列表每页条数
        questionCard: {
            maxLinesDesktop: 8,         // PC端最大显示行数
            maxLinesMobile: 6,          // 移动端最大显示行数
            gradientHeight: 24           // 渐隐高度（像素）
        },
        cartPreviewMaxChars: 120,        // 购物车题目内容预览最大字符数
        questionPreviewMaxChars: 160,    // 列表题目预览最大字符数
        sourceMaxLength: 30              // 题目来源显示最大字符数
    },

    // 学生相关配置
    students: {
        analyticsWindowDays: 30          // 学生数据分析窗口天数
    },

    // 消息提示配置
    messages: {
        autoHideMs: 3000,                // 消息自动隐藏时间（默认，用于success等类型）
        errorAutoHideMs: 8000            // 错误消息自动隐藏时间（延长显示时间）
    }
};

const APP_CONFIG = window.APP_CONFIG;