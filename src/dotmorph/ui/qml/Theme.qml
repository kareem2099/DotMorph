import QtQuick

// Colours and motion for the wheel. name: "dark" (default), "light" or "glass".
QtObject {
    id: theme

    property string name: "dark"
    property bool reduceMotion: false

    // translations (see i18n.py); t("Text") / t("%1 files", n)
    readonly property var strings: (typeof i18n !== "undefined" && i18n) ? i18n.strings : ({})
    readonly property bool rtl: (typeof i18n !== "undefined" && i18n) ? i18n.rtl : false
    function t(text, a1, a2) {
        var out = strings[text] || text
        if (a1 !== undefined) out = out.replace("%1", a1)
        if (a2 !== undefined) out = out.replace("%2", a2)
        return out
    }

    // Multiply every duration by this; 0 means "jump to the end".
    readonly property real motion: reduceMotion ? 0 : 1

    readonly property bool light: name === "light"
    readonly property bool glass: name === "glass"

    // DotSuite brand: emerald on near-black (dotsuite.dev)
    readonly property color accent: "#10B981"
    readonly property color accentHot: "#34D399"
    readonly property color success: "#22C55E"
    readonly property color danger: "#FF5C7A"

    readonly property color backdrop: light ? Qt.rgba(0.97, 0.98, 0.98, 0.95)
                                    : glass ? Qt.rgba(0.06, 0.10, 0.09, 0.55)
                                    : Qt.rgba(0.04, 0.04, 0.04, 0.88)
    readonly property color backdropEdge: light ? Qt.rgba(0.06, 0.73, 0.51, 0.28)
                                        : Qt.rgba(1, 1, 1, glass ? 0.22 : 0.08)
    readonly property color sector: light ? "#E7F2EE" : glass ? Qt.rgba(1, 1, 1, 0.10) : "#1C1C1C"
    readonly property color sectorEdge: light ? "#CFE6DD" : glass ? Qt.rgba(1, 1, 1, 0.16) : "#2A2A2A"
    readonly property color text: light ? "#0A0A0A" : "#FFFFFF"
    readonly property color textDim: light ? "#737373" : Qt.rgba(1, 1, 1, 0.62)
    readonly property color hub: light ? "#FFFFFF" : glass ? Qt.rgba(0.07, 0.12, 0.10, 0.75) : "#121212"
    // settings window surfaces
    readonly property color window: light ? "#FFFFFF" : "#0A0A0A"
    readonly property color card: light ? "#F5F5F5" : "#171717"
    readonly property color cardEdge: light ? "#E5E5E5" : "#262626"

    // One colour per category, used for the hover glow and the category chips.
    function categoryColor(cat) {
        switch (cat) {
        case "image": return "#7C5CFF"
        case "video": return "#FF6B9A"
        case "audio": return "#2FC8F0"
        case "document": return "#FFB547"
        case "tools": return "#10B981"
        }
        return accent
    }

    function categoryLabel(cat) {
        switch (cat) {
        case "image": return t("Image")
        case "video": return t("Video")
        case "audio": return t("Audio")
        case "document": return t("Docs")
        case "tools": return t("Tools")
        }
        return cat
    }

    function ms(value) { return Math.round(value * motion) }
}
