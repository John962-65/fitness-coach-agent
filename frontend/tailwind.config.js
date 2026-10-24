/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        accent: {
          DEFAULT: '#10b981', // emerald-500
          dim: '#059669',
        },
      },
    },
  },
  plugins: [],
}
