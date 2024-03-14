const Color = require('color')
const alpha = (clr, val) => Color(clr).alpha(val).rgb().string()
const lighten = (clr, val) => Color(clr).lighten(val).rgb().string()
const darken = (clr, val) => Color(clr).darken(val).rgb().string()

/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./static/**/*.html"],
  theme: {
    extend: {
      colors: {
        canvas: {
          DEFAULT: '#e72429',
          lighter: lighten('#e72429', 0.2),
          darker: darken('#e72429', 0.2),
        },
      }
    }
  },
  plugins: [
    require('tailwind-scrollbar'),
  ]
}
