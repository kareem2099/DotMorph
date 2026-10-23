import QtQuick
import QtQuick.Effects
import QtQuick.Particles
import QtQuick.Window

// Two-ring radial menu.
//   inner ring : categories (Image, Video, Audio, Docs, Tools)
//   outer fan  : the targets of the hovered category, blooming outward
// With few targets (or one category) the inner ring shows the targets directly.
// half: true opens it as a half wheel out of a screen edge (the edge dock).
Item {
    id: wheel

    required property Theme theme
    property bool isDragging: false
    signal picked(string target)
    signal dismissed()

    property bool half: false
    property string side: "left"
    readonly property real cx: half ? (side === "left" ? hubR + 10 : width - hubR - 10) : width / 2
    readonly property real cy: height / 2
    // the arc the rings may use, in degrees from 12 o'clock clockwise
    readonly property real arcStart: half && side === "right" ? 180 : 0
    readonly property real arcSpan: half ? 180 : 360
    readonly property real hubR: 60
    readonly property real innerA: 72
    readonly property real innerB: 150
    readonly property real outerA: 158
    readonly property real outerB: 234

    property var sectors: bridge.sectors
    readonly property var cats: groupByCategory(sectors)
    readonly property bool flat: cats.length <= 1 || sectors.length <= (half ? 4 : 6)
    readonly property var innerItems: flat ? sectors : cats
    readonly property real innerStep: innerItems.length ? arcSpan / innerItems.length : arcSpan
    // full circle: sector 0 centred at the top; half: sectors fill the arc from its start
    readonly property real innerBase: half ? arcStart : arcStart - innerStep / 2
    // docked right the arc runs bottom -> top; mirror so the first item is still on top
    readonly property bool mirrored: half && side === "right"
    function slot(i, n) { return mirrored ? n - 1 - i : i }

    property int hoverInner: -1
    property int openCat: -1
    property int hoverOuter: -1
    property string phase: "idle"     // idle | busy | done | failed
    property bool optionsOpen: false

    readonly property var fanItems: (!flat && openCat >= 0 && openCat < cats.length && !direct(openCat)) ? cats[openCat].items : []
    readonly property real fanW: fanItems.length ? Math.min(44, (half ? 172 : 330) / fanItems.length) : 0
    readonly property real fanStart: {
        var span = fanW * fanItems.length
        var start = innerBase + (slot(openCat, innerItems.length) + 0.5) * innerStep - span / 2
        return half ? Math.max(arcStart + 4, Math.min(start, arcStart + arcSpan - 4 - span)) : start
    }

    // A category with a single option is a shortcut: hovering shows it, clicking converts.
    function direct(i) { return !flat && i >= 0 && i < cats.length && cats[i].items.length === 1 }
    function innerTarget(i) {
        if (i < 0 || i >= innerItems.length) return null
        return flat ? innerItems[i] : (direct(i) ? cats[i].items[0] : null)
    }
    readonly property var hoveredTarget: hoverOuter >= 0 && hoverOuter < fanItems.length ? fanItems[hoverOuter]
                                       : innerTarget(hoverInner)
    readonly property color glowColor: hoveredTarget ? theme.categoryColor(hoveredTarget.category)
                                     : (!flat && openCat >= 0 && openCat < cats.length ? theme.categoryColor(cats[openCat].id)
                                     : theme.accent)

    function groupByCategory(list) {
        var order = [], map = {}
        for (var i = 0; i < list.length; i++) {
            var c = list[i].category
            if (!(c in map)) { map[c] = { id: c, label: theme.categoryLabel(c), category: c, items: [] }; order.push(map[c]) }
            map[c].items.push(list[i])
        }
        return order
    }

    onSectorsChanged: { hoverInner = -1; hoverOuter = -1; openCat = -1; phase = "idle" }
    Connections {
        target: bridge
        function onBusyChanged() {
            if (!bridge.busy) return
            wheel.phase = "busy"
            wheel.hoverInner = -1
            wheel.hoverOuter = -1
        }
    }

    // ---- moving the window ----------------------------------------------------------------
    property bool moving: false
    opacity: moving ? 0.55 : 1  // see what's underneath while dragging
    Behavior on opacity { NumberAnimation { duration: wheel.theme.ms(150) } }
    function startMove() {
        moving = true
        moveSettle.restart()
        var w = wheel.Window.window
        return w ? w.startSystemMove() : false
    }
    function settleMove() { moveSettle.restart() }
    Timer {
        id: moveSettle
        interval: 400
        onTriggered: {
            wheel.moving = false
            if (dock.mode === "free") dock.dragEnded()  // touching a screen edge docks it
        }
    }
    Connections {
        target: wheel.Window.window
        function onXChanged() { if (wheel.moving) moveSettle.restart() }
        function onYChanged() { if (wheel.moving) moveSettle.restart() }
    }

    function celebrate() {
        phase = "done"
        hub.pulse()
        if (theme.motion > 0) burst.burst(110)
    }
    function fail() {
        phase = "failed"
        hub.pulse()
        shake.restart()
    }

    // ---- keyboard ------------------------------------------------------------------------
    focus: true
    Keys.onPressed: (e) => {
        if (e.key === Qt.Key_O && phase !== "busy") { optionsOpen = !optionsOpen; e.accepted = true; return }
        if (optionsOpen) {
            if (e.key === Qt.Key_Return || e.key === Qt.Key_Enter || e.key === Qt.Key_Backspace) optionsOpen = false
            e.accepted = true
            return
        }
        if (phase === "busy") return
        var n
        if (e.key === Qt.Key_Right || e.key === Qt.Key_Tab) { move(1); e.accepted = true }
        else if (e.key === Qt.Key_Left || e.key === Qt.Key_Backtab) { move(-1); e.accepted = true }
        else if (e.key === Qt.Key_Up || e.key === Qt.Key_Return || e.key === Qt.Key_Enter || e.key === Qt.Key_Space) { activate(); e.accepted = true }
        else if (e.key === Qt.Key_Down || e.key === Qt.Key_Backspace) {
            if (hoverOuter >= 0) { hoverOuter = -1; hoverInner = openCat }
            e.accepted = true
        } else if (e.key >= Qt.Key_1 && e.key <= Qt.Key_9) {
            var idx = e.key - Qt.Key_1
            if (hoverOuter >= 0 || (openCat >= 0 && !flat && hoverInner < 0)) { if (idx < fanItems.length) { hoverOuter = idx; activate() } }
            else if (idx < innerItems.length) { hoverInner = idx; if (!flat) openCat = idx; activate() }
            e.accepted = true
        }
    }
    function move(d) {
        if (hoverOuter >= 0) {
            hoverOuter = (hoverOuter + d + fanItems.length) % fanItems.length
        } else {
            var n = innerItems.length
            if (n === 0) return
            hoverInner = hoverInner < 0 ? 0 : (hoverInner + d + n) % n
            if (!flat) openCat = hoverInner
        }
    }
    function activate() {
        if (hoverOuter >= 0) { picked(fanItems[hoverOuter].id); return }
        if (hoverInner < 0) { move(1); return }
        var t = innerTarget(hoverInner)
        if (t) { picked(t.id); return }
        openCat = hoverInner; hoverInner = -1; hoverOuter = 0
    }

    // ---- shake on failure ----------------------------------------------------------------
    transform: Translate { id: shakeT }
    SequentialAnimation {
        id: shake
        NumberAnimation { target: shakeT; property: "x"; to: -14; duration: wheel.theme.ms(55) }
        NumberAnimation { target: shakeT; property: "x"; to: 12; duration: wheel.theme.ms(70) }
        NumberAnimation { target: shakeT; property: "x"; to: -8; duration: wheel.theme.ms(65) }
        NumberAnimation { target: shakeT; property: "x"; to: 5; duration: wheel.theme.ms(60) }
        NumberAnimation { target: shakeT; property: "x"; to: 0; duration: wheel.theme.ms(60) }
    }

    // ---- backdrop ------------------------------------------------------------------------
    Rectangle {
        id: backdrop
        x: wheel.cx - width / 2
        y: wheel.cy - height / 2
        property real rad: (fanItems.length > 0 ? wheel.outerB : (wheel.sectors.length ? wheel.innerB : wheel.hubR + 36)) + 14
        Behavior on rad { NumberAnimation { duration: wheel.theme.ms(320); easing.type: Easing.OutBack; easing.overshoot: 0.9 } }
        width: rad * 2
        height: width
        radius: width / 2
        color: wheel.theme.backdrop
        border.width: wheel.isDragging ? 2.5 : 1
        border.color: wheel.isDragging ? wheel.theme.accent : wheel.theme.backdropEdge
    }

    // drag-over / empty-state ripples
    Repeater {
        model: 3
        delegate: Rectangle {
            id: ripple
            required property int index
            x: wheel.cx - width / 2
            y: wheel.cy - height / 2
            property real k: 0
            width: (wheel.hubR + 10) * 2 * (1 + 1.6 * k)
            height: width
            radius: width / 2
            color: "transparent"
            border.width: 2
            border.color: wheel.theme.accent
            opacity: (wheel.isDragging ? 0.7 : 0.25) * (1 - k)
            visible: wheel.theme.motion > 0 && (wheel.isDragging || wheel.sectors.length === 0)
            SequentialAnimation on k {
                running: ripple.visible
                loops: Animation.Infinite
                PauseAnimation { duration: ripple.index * 520 }
                NumberAnimation { from: 0; to: 1; duration: 1560; easing.type: Easing.OutCubic }
            }
        }
    }

    // ---- rings (one glowing layer) -------------------------------------------------------
    Item {
        id: rings
        anchors.fill: parent
        // step back while converting, almost vanish once the result is shown
        opacity: wheel.optionsOpen ? 0.12
               : wheel.phase === "busy" ? 0.35 : (wheel.phase === "idle" ? 1 : 0.1)
        scale: wheel.phase === "idle" ? 1 : 0.94
        Behavior on opacity { NumberAnimation { duration: wheel.theme.ms(320) } }
        Behavior on scale { NumberAnimation { duration: wheel.theme.ms(320); easing.type: Easing.OutCubic } }

        // magnetic parallax: the rings lean a little toward the pointer
        property real tx: 0
        property real ty: 0
        Behavior on tx { NumberAnimation { duration: wheel.theme.ms(220); easing.type: Easing.OutCubic } }
        Behavior on ty { NumberAnimation { duration: wheel.theme.ms(220); easing.type: Easing.OutCubic } }
        transform: Translate { x: rings.tx; y: rings.ty }

        layer.enabled: wheel.theme.motion > 0
        layer.effect: MultiEffect {
            shadowEnabled: true
            shadowColor: Qt.rgba(wheel.glowColor.r, wheel.glowColor.g, wheel.glowColor.b,
                                 wheel.hoverInner >= 0 || wheel.hoverOuter >= 0 ? 0.7 : 0.22)
            shadowBlur: 1.0
            blurMax: 32
            shadowHorizontalOffset: 0
            shadowVerticalOffset: 0
            shadowScale: 1.0
        }

        Repeater {
            model: wheel.innerItems
            delegate: RingSector {
                required property var modelData
                required property int index
                theme: wheel.theme
                cx: wheel.cx; cy: wheel.cy
                innerR: wheel.innerA; outerR: wheel.innerB
                startDeg: wheel.innerBase + wheel.slot(index, wheel.innerItems.length) * wheel.innerStep
                sweepDeg: wheel.innerStep
                readonly property bool shortcut: !wheel.flat && modelData.items.length === 1
                label: shortcut ? modelData.items[0].label : modelData.label
                category: modelData.category
                showIcon: !wheel.flat
                sub: wheel.flat ? "" : (shortcut ? modelData.label : wheel.theme.t("%1 options", modelData.items.length))
                hovered: wheel.hoverInner === index
                selected: !wheel.flat && wheel.openCat === index
                busy: wheel.phase !== "idle"
                order: index
            }
        }

        Repeater {
            model: wheel.fanItems
            delegate: RingSector {
                required property var modelData
                required property int index
                theme: wheel.theme
                cx: wheel.cx; cy: wheel.cy
                innerR: wheel.outerA; outerR: wheel.outerB
                startDeg: wheel.fanStart + wheel.slot(index, wheel.fanItems.length) * wheel.fanW
                sweepDeg: wheel.fanW
                gapPx: 4
                label: modelData.label
                category: modelData.category
                hovered: wheel.hoverOuter === index
                busy: wheel.phase !== "idle"
                order: Math.abs(index - (wheel.fanItems.length - 1) / 2)  // bloom from the middle
                stagger: 26
                fromScale: 0.82
                spin: 0
            }
        }
    }

    Hub {
        id: hub
        theme: wheel.theme
        x: wheel.cx - width / 2
        y: wheel.cy - height / 2
        r: wheel.hubR
        mode: wheel.phase
        progress: bridge.progress
        tint: wheel.glowColor
        cancelHint: mouse.overHub && wheel.phase === "busy"
        title: wheel.isDragging ? wheel.theme.t("Drop it") : (wheel.hoveredTarget ? "→ " + wheel.hoveredTarget.label : bridge.fileLabel)
        subtitle: wheel.isDragging ? "" : (wheel.hoveredTarget ? wheel.theme.t("click to convert")
                 : bridge.status !== "" ? bridge.status
                 : (!wheel.flat && wheel.openCat >= 0 ? wheel.cats[wheel.openCat].label
                 : (wheel.sectors.length ? (bridge.optionsSummary || wheel.theme.t("pick a format")) : "")))
    }

    // status chip under the wheel (result / error)
    Rectangle {
        id: chip
        visible: opacity > 0
        opacity: bridge.status !== "" && (wheel.phase === "done" || wheel.phase === "failed") ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: wheel.theme.ms(200) } }
        x: Math.max(8, Math.min(wheel.cx - width / 2, wheel.width - width - 8))
        y: wheel.cy + wheel.hubR + 22
        width: Math.min(wheel.width - 16, 360, chipText.implicitWidth + 28)
        height: chipText.height + 12
        radius: Math.min(14, height / 2)
        color: wheel.phase === "failed" ? Qt.rgba(1, 0.36, 0.48, 0.18)
             : wheel.phase === "done" ? Qt.rgba(0.18, 0.83, 0.55, 0.18) : Qt.rgba(1, 1, 1, 0.08)
        border.color: wheel.phase === "failed" ? wheel.theme.danger : wheel.phase === "done" ? wheel.theme.success : wheel.theme.backdropEdge
        Text {
            id: chipText
            anchors.centerIn: parent
            width: Math.min(chip.width - 28, implicitWidth)
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.Wrap
            maximumLineCount: 2
            text: bridge.status
            color: wheel.theme.text
            font.pixelSize: 12
            elide: Text.ElideRight
        }
    }

    // ---- success burst -------------------------------------------------------------------
    ParticleSystem { id: particles; running: wheel.theme.motion > 0 }
    Emitter {
        id: burst
        system: particles
        x: wheel.cx; y: wheel.cy; width: 1; height: 1
        emitRate: 0
        lifeSpan: 1100; lifeSpanVariation: 350
        size: 14; sizeVariation: 8; endSize: 2
        velocity: AngleDirection { angleVariation: 360; magnitude: 300; magnitudeVariation: 160 }
        acceleration: PointDirection { y: 240 }
    }
    ImageParticle {
        system: particles
        source: "qrc:///particleresources/glowdot.png"
        color: wheel.theme.success
        colorVariation: 0.9
        alpha: 0.95
        entryEffect: ImageParticle.Scale
    }

    OptionsPanel {
        id: optionsPanel
        objectName: "optionsPanel"
        theme: wheel.theme
        anchors.centerIn: parent
        width: Math.min(330, wheel.width - 12)
        open: wheel.optionsOpen
        onClosed: wheel.optionsOpen = false
        z: 30
    }

    // ---- pointer -------------------------------------------------------------------------
    MouseArea {
        id: mouse
        anchors.fill: parent
        enabled: !wheel.optionsOpen
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        property bool overHub: false
        // Press + move = drag the whole wheel around; only a press without movement clicks.
        property point pressAt: Qt.point(0, 0)
        property bool dragged: false
        property bool systemMove: false

        function polar(mx, my) {
            var dx = mx - wheel.cx, dy = my - wheel.cy
            return { d: Math.sqrt(dx * dx + dy * dy), a: (Math.atan2(dy, dx) * 180 / Math.PI + 90 + 360) % 360 }
        }
        function innerAt(a) {
            var n = wheel.innerItems.length
            if (!n) return -1
            var rel = ((a - wheel.innerBase) % 360 + 360) % 360
            return rel < wheel.arcSpan ? wheel.slot(Math.min(n - 1, Math.floor(rel / wheel.innerStep)), n) : -1
        }
        function fanAt(a) {
            var n = wheel.fanItems.length
            if (!n) return -1
            var d = ((a - wheel.fanStart) % 360 + 360) % 360
            return d < wheel.fanW * n ? wheel.slot(Math.floor(d / wheel.fanW), n) : -1
        }

        onPressed: (m) => { pressAt = Qt.point(m.x, m.y); dragged = false }
        onReleased: { if (wheel.half && dragged) dock.slideEnded(); wheel.settleMove() }
        onCanceled: { dragged = false; wheel.settleMove() }

        onPositionChanged: (m) => {
            if (pressed && (m.buttons & Qt.LeftButton)) {
                var mx = m.x - pressAt.x, my = m.y - pressAt.y
                if (wheel.half) {  // docked: slide along the edge, or pull it off the edge
                    var away = wheel.side === "left" ? mx : -mx
                    if (!dragged && mx * mx + my * my > 36) {
                        dragged = true
                        wheel.hoverInner = -1
                        wheel.hoverOuter = -1
                    }
                    if (dragged && away > 90) {
                        dock.undock()
                        wheel.startMove()
                    } else if (dragged) {
                        dock.slide(my)
                    }
                    return
                }
                if (!dragged && mx * mx + my * my > 36) {
                    dragged = true
                    wheel.hoverInner = -1
                    wheel.hoverOuter = -1
                    systemMove = wheel.startMove()
                }
                if (dragged) {
                    if (!systemMove) {  // window manager can't move us: do it by hand
                        var w = wheel.Window.window
                        w.x += mx
                        w.y += my
                    }
                    return
                }
            }
            var p = polar(m.x, m.y)
            overHub = p.d < wheel.hubR
            var lean = Math.min(1, p.d / wheel.outerB) * 6
            rings.tx = (m.x - wheel.cx) / Math.max(1, p.d) * lean
            rings.ty = (m.y - wheel.cy) / Math.max(1, p.d) * lean
            if (wheel.phase === "busy") return
            if (p.d >= wheel.innerA - 4 && p.d <= wheel.innerB + 3) {
                wheel.hoverInner = innerAt(p.a)
                wheel.hoverOuter = -1
                if (!wheel.flat) wheel.openCat = wheel.hoverInner
            } else if (wheel.fanItems.length && p.d > wheel.innerB + 3 && p.d <= wheel.outerB + 12) {
                wheel.hoverOuter = fanAt(p.a)
                wheel.hoverInner = -1
            } else {
                wheel.hoverInner = -1
                wheel.hoverOuter = -1
            }
        }
        onExited: { overHub = false; wheel.hoverInner = -1; wheel.hoverOuter = -1; rings.tx = 0; rings.ty = 0 }
        onClicked: (m) => {
            if (dragged) { dragged = false; return }
            var p = polar(m.x, m.y)
            if (m.button === Qt.RightButton) { wheel.dismissed(); return }
            if (wheel.phase === "busy") { if (p.d < wheel.hubR) bridge.cancel(); return }
            if (wheel.hoverOuter >= 0) wheel.picked(wheel.fanItems[wheel.hoverOuter].id)
            else if (wheel.hoverInner >= 0) {
                var t = wheel.innerTarget(wheel.hoverInner)
                if (t) wheel.picked(t.id)
                else wheel.openCat = wheel.hoverInner
            } else if (p.d > backdrop.rad + 4) wheel.dismissed()
        }
    }
}
