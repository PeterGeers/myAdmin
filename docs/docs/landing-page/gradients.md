# Gradient Achtergronden

## Overzicht

Met gradient achtergronden geef je individuele blokken op je landing page een kleurrijk verloop als achtergrond. Je kunt kiezen uit 8 kant-en-klare presets of zelf een CSS gradient invoeren voor volledige controle.

## Beschikbare presets

| Preset naam | Kleurverloop                |
| ----------- | --------------------------- |
| Sunset      | warm oranje naar rood       |
| Ocean       | diepblauw naar turquoise    |
| Forest      | donkergroen naar lichtgroen |
| Peach       | zacht roze naar perzik      |
| Night       | donkerpaars naar nachtblauw |
| Warm        | warm geel naar oranje       |
| Sky         | lichtblauw naar wit         |
| Gold        | goudgeel naar amber         |

## Gradient toepassen op een blok

1. Klik op het blok dat je wilt bewerken
2. Open het **Instellingen** paneel aan de rechterkant
3. Stel **Achtergrond type** in op **Gradient**
4. Kies een preset door op de gewenste gradient-knop te klikken
5. Bekijk het resultaat in de **live preview strip** bovenaan de gradient-selector

!!! tip "Snel wisselen"
Je kunt direct tussen presets wisselen door op een andere gradient-knop te klikken. De preview strip toont meteen het nieuwe verloop.

## Vrije CSS gradient invoer

Gevorderde gebruikers kunnen een eigen CSS gradient waarde invoeren in het tekstveld onder de preset-knoppen. Typ een geldige CSS gradient-waarde, bijvoorbeeld:

```css
linear-gradient(135deg, #667eea 0%, #764ba2 100%)
```

!!! note "Ondersteunde formaten"
Alle standaard CSS gradient-formaten worden ondersteund: `linear-gradient()`, `radial-gradient()` en `conic-gradient()`. De waarde wordt direct toegepast als `background` eigenschap van het blok.

## Live preview strip

De preview strip is een smalle balk boven de gradient-selector die het geselecteerde verloop in realtime toont. Zodra je een preset kiest of een eigen waarde invoert, wordt de strip bijgewerkt zodat je direct kunt zien hoe het verloop eruitziet — zonder het blok op de pagina te hoeven zoeken.

!!! warning "Ongeldige CSS"
Als je een ongeldige CSS gradient invoert, toont de preview strip geen verloop. Controleer de syntax en probeer opnieuw.
