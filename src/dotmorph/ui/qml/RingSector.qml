import QtQuick
import QtQuick.Shapes

// One ring sector, drawn on the GPU. Fills its parent; (cx, cy) is the wheel centre.
// Angles are in degrees from 12 o'clock, clockwise.
Item {
    id: s

    required property Theme theme
    property real cx: width / 2
    property real cy: height / 2
    property real innerR: 70
    property real outerR: 150
    property real startDeg: 0
    property real sweepDeg: 90
    property real gapPx: 5

    property string label: ""
    property string sub: ""          // small second line, e.g. "9 formats"
    property string category: ""
    property bool showIcon: false
    property bool hovered: false
    property bool selected: false     // category whose fan is open
    property bool busy: false        // no hover lift while converting

    // Intro: staggered fly-out from the centre with a small spin.
    property int order: 0
    property int stagger: 38
    property real fromScale: 0.25
    property real spin: -28
    property real reveal: 0

    readonly property color hot: theme.categoryColor(category)
    // label colour: white on a lit sector; on the light theme only once really hovered
    readonly property real ink: theme.light ? Math.max(0, (lift - 0.6) / 0.4) : lift
    readonly property real midDeg: startDeg + sweepDeg / 2
    readonly property real midRad: (midDeg - 90) * Math.PI / 180
    readonly property real rMid: (innerR + outerR) / 2

    // 0 idle, ~0.5 selected, 1 hovered; animated so colour, push and size move together.
    property real lift: busy ? 0 : (hovered ? 1 : (selected ? 0.55 : 0))
    Behavior on lift { NumberAnimation { duration: s.theme.ms(170); easing.type: Easing.OutCubic } }
    property real pop: hovered ? 1 : 0
    Behavior on pop { NumberAnimation { duration: s.theme.ms(260); easing.type: Easing.OutBack; easing.overshoot: 2.2 } }

    function mix(a, b, t) {
        return Qt.rgba(a.r + (b.r - a.r) * t, a.g + (b.g - a.g) * t,
                       a.b + (b.b - a.b) * t, a.a + (b.a - a.a) * t)
    }

    anchors.fill: parent
    transformOrigin: Item.Center
    scale: fromScale + (1 - fromScale) * reveal
    rotation: (1 - reveal) * spin
    opacity: Math.min(1, reveal)

    transform: Translate {
        x: Math.cos(s.midRad) * 7 * s.lift
        y: Math.sin(s.midRad) * 7 * s.lift
    }

    Component.onCompleted: intro.start()
    SequentialAnimation {
        id: intro
        PauseAnimation { duration: s.theme.ms(s.order * s.stagger) }
        NumberAnimation {
            target: s; property: "reveal"; to: 1
            duration: s.theme.ms(440); easing.type: Easing.OutBack; easing.overshoot: 1.25
        }
    }

    Shape {
        id: shape
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer

        readonly property real oR: s.outerR + 5 * s.lift
        readonly property real iR: s.innerR
        readonly property real gapO: s.gapPx / oR * 180 / Math.PI
        readonly property real gapI: s.gapPx / iR * 180 / Math.PI
        readonly property real a0: s.startDeg - 90 + gapO / 2
        readonly property real sweepO: Math.max(0.5, s.sweepDeg - gapO)
        readonly property real b0: s.startDeg - 90 + s.sweepDeg - gapI / 2
        readonly property real sweepI: Math.max(0.5, s.sweepDeg - gapI)

        // ring sector as an SVG path: outer arc clockwise, inner arc back
        function pt(r, deg) {
            var a = deg * Math.PI / 180
            return (s.cx + r * Math.cos(a)).toFixed(2) + " " + (s.cy + r * Math.sin(a)).toFixed(2)
        }
        readonly property string d: {
            var bigO = sweepO > 180 ? 1 : 0, bigI = sweepI > 180 ? 1 : 0
            if (s.sweepDeg >= 359.9) {  // a full ring: two half arcs each way
                return "M " + pt(oR, -90) + " A " + oR + " " + oR + " 0 1 1 " + pt(oR, 90)
                     + " A " + oR + " " + oR + " 0 1 1 " + pt(oR, -90)
                     + " M " + pt(iR, -90) + " A " + iR + " " + iR + " 0 1 0 " + pt(iR, 90)
                     + " A " + iR + " " + iR + " 0 1 0 " + pt(iR, -90) + " Z"
            }
            return "M " + pt(oR, a0) + " A " + oR + " " + oR + " 0 " + bigO + " 1 " + pt(oR, a0 + sweepO)
                 + " L " + pt(iR, b0) + " A " + iR + " " + iR + " 0 " + bigI + " 0 " + pt(iR, b0 - sweepI) + " Z"
        }

        ShapePath {
            strokeWidth: 1.2
            strokeColor: s.mix(s.theme.sectorEdge, Qt.lighter(s.hot, 1.35), s.lift)
            joinStyle: ShapePath.RoundJoin
            fillGradient: RadialGradient {
                centerX: s.cx; centerY: s.cy; focalX: s.cx; focalY: s.cy
                centerRadius: shape.oR
                focalRadius: 0
                GradientStop { position: s.innerR / shape.oR; color: s.mix(s.theme.sector, Qt.darker(s.hot, 1.25), s.lift) }
                GradientStop { position: 1.0; color: s.mix(s.theme.sector, Qt.lighter(s.hot, 1.15), s.lift) }
            }

            PathSvg { path: shape.d }
        }
    }

    Column {
        id: content
        spacing: 2
        x: s.cx + s.rMid * Math.cos(s.midRad) - width / 2
        y: s.cy + s.rMid * Math.sin(s.midRad) - height / 2
        scale: 1 + 0.14 * s.pop
        rotation: -s.rotation  // labels stay upright during the spin-in

        CategoryIcon {
            visible: s.showIcon
            anchors.horizontalCenter: parent.horizontalCenter
            width: 22; height: 22
            category: s.category
            color: s.mix(s.theme.text, Qt.rgba(1, 1, 1, 1), s.ink)
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: s.label
            color: s.mix(s.theme.text, Qt.rgba(1, 1, 1, 1), s.ink)
            font.pixelSize: s.showIcon ? 13 : (s.sweepDeg < 34 ? 12 : 15)
            font.bold: true
            font.letterSpacing: 0.5
        }
        Text {
            visible: s.sub !== ""
            anchors.horizontalCenter: parent.horizontalCenter
            text: s.sub
            color: s.mix(s.theme.textDim, Qt.rgba(1, 1, 1, 0.8), s.ink)
            font.pixelSize: 10
        }
    }
}
