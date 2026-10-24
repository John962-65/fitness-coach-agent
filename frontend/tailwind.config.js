/** @type {import('tailwindcss').Config} */
// 统一设计变量（视觉规范 v2）：暖白底 / 深墨字 / 青柠强调。
// 页面只允许引用这里的语义色，不再各自硬编码。
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // 背景 / 表面
        canvas: '#F6F7F3',
        surface: '#FFFFFF',
        night: '#18251D', // 深色表面（主视觉卡 / 侧栏 / 训练执行）
        nightSoft: '#22332880', // 夜色表面上的半透明层
        // 文字
        ink: '#17231B',
        muted: '#68756D',
        faint: '#98A49C', // 仅限辅助时间戳等三级信息
        // 线
        line: '#E7EBE5',
        lineStrong: '#D6DDD4',
        // 品牌强调
        accent: {
          DEFAULT: '#B8EE70',
          dim: '#A3DD57', // pressed
          soft: '#EFFADF', // 浅底
          deep: '#3D5A26', // 深色底上的可读强调文字
        },
      },
      fontFamily: {
        sans: [
          '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'PingFang SC',
          'Hiragino Sans GB', 'Microsoft YaHei', 'Helvetica Neue', 'Helvetica',
          'Arial', 'sans-serif',
        ],
      },
      fontSize: {
        // 正文 ≥14px 的清晰层级
        '2xs': ['11px', '14px'],
        xs: ['12px', '17px'],
        sm: ['14px', '20px'],
        base: ['15px', '22px'],
        lg: ['17px', '24px'],
        xl: ['20px', '28px'],
        '2xl': ['24px', '32px'],
        '3xl': ['30px', '38px'],
        '4xl': ['36px', '44px'],
      },
      borderRadius: {
        xl: '14px',
        '2xl': '18px',
        '3xl': '24px',
      },
      boxShadow: {
        card: '0 1px 2px rgba(23, 35, 27, 0.05), 0 2px 8px rgba(23, 35, 27, 0.04)',
        pop: '0 8px 24px rgba(23, 35, 27, 0.14)',
        bar: '0 -1px 0 rgba(23,35,27,0.06), 0 -6px 20px rgba(23, 35, 27, 0.06)',
      },
      keyframes: {
        'fade-up': {
          from: { opacity: '0', transform: 'translateY(6px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        'sheet-up': {
          from: { transform: 'translateY(24px)', opacity: '0.6' },
          to: { transform: 'translateY(0)', opacity: '1' },
        },
        pulseSoft: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.55' },
        },
      },
      animation: {
        'fade-up': 'fade-up 0.25s ease-out both',
        'sheet-up': 'sheet-up 0.22s ease-out both',
        'pulse-soft': 'pulseSoft 1.6s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
