/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // 深色主题核心色板
        bg: {
          base:    '#0d0f14',   // 最深背景
          surface: '#13161e',   // 卡片/面板
          elevated:'#1a1e2a',   // 悬浮层
          border:  '#252a38',   // 分割线
        },
        accent: {
          cyan:    '#00d4ff',
          'cyan-dim': '#0099bb',
          violet:  '#8b5cf6',
          amber:   '#f59e0b',
          emerald: '#10b981',
          rose:    '#f43f5e',
        },
        text: {
          primary:   '#e8eaf0',
          secondary: '#8b9ab5',
          muted:     '#4a5568',
        },
      },
      fontFamily: {
        sans:  ['"DM Sans"', 'sans-serif'],
        mono:  ['"JetBrains Mono"', 'monospace'],
        display: ['"Syne"', 'sans-serif'],
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'fade-in':    'fadeIn 0.3s ease-out',
        'slide-in':   'slideIn 0.3s ease-out',
        'shimmer':    'shimmer 2s linear infinite',
      },
      keyframes: {
        fadeIn: {
          '0%':   { opacity: '0', transform: 'translateY(4px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        slideIn: {
          '0%':   { opacity: '0', transform: 'translateX(-8px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
        shimmer: {
          '0%':   { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
      },
      boxShadow: {
        'glow-cyan':   '0 0 20px rgba(0, 212, 255, 0.15)',
        'glow-violet': '0 0 20px rgba(139, 92, 246, 0.15)',
        'panel':       '0 4px 24px rgba(0, 0, 0, 0.4)',
      },
    },
  },
  plugins: [],
}
