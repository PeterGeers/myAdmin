# Gradient Backgrounds

## Overview

With gradient backgrounds you give individual blocks on your landing page a colourful gradient as a background. You can choose from 8 ready-made presets or enter your own CSS gradient for full control.

## Available presets

| Preset name | Colour gradient           |
| ----------- | ------------------------- |
| Sunset      | warm orange to red        |
| Ocean       | deep blue to turquoise    |
| Forest      | dark green to light green |
| Peach       | soft pink to peach        |
| Night       | dark purple to night blue |
| Warm        | warm yellow to orange     |
| Sky         | light blue to white       |
| Gold        | golden yellow to amber    |

## Applying a gradient to a block

1. Click on the block you want to edit
2. Open the **Settings** panel on the right-hand side
3. Set **Background type** to **Gradient**
4. Choose a preset by clicking the desired gradient button
5. View the result in the **live preview strip** at the top of the gradient selector

!!! tip "Quick switching"
You can switch between presets instantly by clicking a different gradient button. The preview strip immediately shows the new gradient.

## Custom CSS gradient input

Advanced users can enter a custom CSS gradient value in the text field below the preset buttons. Type a valid CSS gradient value, for example:

```css
linear-gradient(135deg, #667eea 0%, #764ba2 100%)
```

!!! note "Supported formats"
All standard CSS gradient formats are supported: `linear-gradient()`, `radial-gradient()` and `conic-gradient()`. The value is applied directly as the `background` property of the block.

## Live preview strip

The preview strip is a narrow bar above the gradient selector that shows the selected gradient in real time. As soon as you choose a preset or enter a custom value, the strip updates so you can immediately see what the gradient looks like — without having to find the block on the page.

!!! warning "Invalid CSS"
If you enter an invalid CSS gradient, the preview strip will not show a gradient. Check the syntax and try again.
