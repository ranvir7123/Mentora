pragma Singleton
import QtQuick

// Every colour, size, space, corner and duration the screens use. No other QML file holds a colour.
// The look is "Highlighter": a desk at night. Warm graphite surfaces, and colour only where a highlighter
// would go: on progress, on the one thing to press, on a word that matters.
QtObject {
    // Surfaces: one warm graphite base, two steps above it, one border.
    readonly property color bg: "#1C1B19"
    readonly property color surface1: "#262522"
    readonly property color surface2: "#312F2B"
    readonly property color border: "#433F39"

    // Yellow highlighter: progress, the main button and the "you are here" mark only.
    readonly property color accent: "#F5E15A"
    readonly property color accentEdge: "#B8A522"

    // The mascot keeps its own coral, and the ring around the cell it points at is the same coral, so on a
    // white sheet the two read as one character.
    readonly property color mascot: "#FF7A45"
    readonly property color mascotEdge: "#C9521F"        // its curl
    readonly property color mascotShade: "#E8622E"       // its belly and cheeks
    readonly property color ring: "#FF7A45"

    // Orange highlighter: points, streaks and celebrations only.
    readonly property color reward: "#FFB05C"
    readonly property color rewardEdge: "#C47A27"

    readonly property color right: "#8EE88B"
    readonly property color rightEdge: "#58B055"
    readonly property color notYet: "#FF8FB1"
    readonly property color notYetEdge: "#C25A7A"
    // The banners' backgrounds: green and pink laid thinly over the base, so their words keep 4.5:1.
    readonly property color rightTint: "#2A3A27"
    readonly property color notYetTint: "#3D2830"

    readonly property color text: "#F2EFE8"
    readonly property color muted: "#ABA69C"
    readonly property color onColour: "#1C1B19"          // words on any highlighter colour

    // Course colours: three more highlighters, told apart from yellow, orange, green and pink.
    readonly property color courseExcel: "#9BD7FF"
    readonly property color coursePython: "#C9B6FF"
    readonly property color courseMeta: "#F2C9A0"

    function course(name) {
        return name === "coursePython" ? coursePython : name === "courseMeta" ? courseMeta : courseExcel
    }

    // Type: Archivo for everything (its digits are equal width), and its wide cut for the few big words.
    readonly property string fontDisplay: "Archivo Expanded"
    readonly property string fontHeading: "Archivo"
    readonly property string fontBody: "Archivo"
    readonly property real tightDisplay: -0.5            // letter spacing on the wide cut, in pixels
    readonly property int size12: 12
    readonly property int size14: 14
    readonly property int size16: 16
    readonly property int size20: 20
    readonly property int size24: 24
    readonly property int size32: 32
    readonly property int size48: 48

    readonly property int space4: 4
    readonly property int space8: 8
    readonly property int space12: 12
    readonly property int space16: 16
    readonly property int space24: 24
    readonly property int space32: 32
    readonly property int space48: 48

    // Three corner sizes, no more, all small: things here are cut paper and keycaps, not pills.
    readonly property int radiusSmall: 2
    readonly property int radiusMedium: 4
    readonly property int radiusLarge: 8

    readonly property int edge: 3                        // a key's darker bottom edge
    readonly property int hairline: 1                    // a ruled line between parts of a page

    readonly property int durFast: 150
    readonly property int durNormal: 220
    readonly property int durPanel: 300

    // The see-through veil behind a dialog or a dimmed lesson circle.
    readonly property color veil: "#B31C1B19"
    readonly property color clear: "transparent"
}
