/** @type {import('tailwindcss').Config} */
export default {
  // 扫描以下文件中的Tailwind类名，生成对应的CSS
  content: [
    "./index.html",                    // HTML入口
    "./src/**/*.{js,ts,jsx,tsx}",      // 所有源码文件
  ],
  theme: {
    extend: {},  // 扩展默认主题（可添加自定义颜色、字体等）
  },
  plugins: [],   // Tailwind插件（可添加表单、排版等插件）
}
