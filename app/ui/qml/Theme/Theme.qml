pragma Singleton
import QtQuick

// Every colour, size, space, corner and duration the screens use. No other QML file holds a colour.
QtObject {
    // Surfaces: one deep navy base, two steps above it, one border.
    readonly property color bg: "#151A2E"
    readonly property color surface1: "#1E2440"
    readonly property color surface2: "#282F52"
    readonly property color border: "#363E66"

    // Coral: progress, the main button, the ring and the mascot's body only.
    readonly property color accent: "#FF7A45"
    readonly property color accentEdge: "#C9521F"
    readonly property color accentShade: "#E8622E"      // the mascot's belly and cheeks

    // Gold: points, streaks and celebrations only.
    readonly property color reward: "#FFC53D"
    readonly property color rewardEdge: "#C98F0B"

    readonly property color right: "#3DDC97"
    readonly property color rightEdge: "#1FA46C"
    readonly property color notYet: "#FF6B81"
    readonly property color notYetEdge: "#C9405A"
    // The banners' backgrounds: mint and rose laid thinly over surface1, so their words keep 4.5:1.
    readonly property color rightTint: "#23414E"
    readonly property color notYetTint: "#3E2E49"

    readonly property color text: "#EEF1FA"
    readonly property color muted: "#9AA3C0"
    readonly property color onColour: "#151A2E"          // words on coral, gold, mint and rose

    // Course colours: solid, told apart from coral, gold, mint and rose.
    readonly property color courseExcel: "#36C5E0"
    readonly property color coursePython: "#7B93FF"
    readonly property color courseMeta: "#C08BFF"

    function course(name) {
        return name === "coursePython" ? coursePython : name === "courseMeta" ? courseMeta : courseExcel
    }

    // Type: Fredoka for headings, Nunito for text and every number (its digits are equal width).
    readonly property string fontHeading: "Fredoka"
    readonly property string fontBody: "Nunito"
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

    // Three corner sizes, no more.
    readonly property int radiusSmall: 6
    readonly property int radiusMedium: 12
    readonly property int radiusLarge: 20

    readonly property int edge: 4                        // the chunky button's darker bottom edge

    readonly property int durFast: 150
    readonly property int durNormal: 220
    readonly property int durPanel: 300

    // The see-through veil behind a dialog or a dimmed lesson circle.
    readonly property color veil: "#B3151A2E"
    readonly property color clear: "transparent"
}
