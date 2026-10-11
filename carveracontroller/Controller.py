#!/usr/bin/python


import hashlib
import json
import logging
import math
import os
import re
import sys
import threading
import time
import weakref
import webbrowser
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

logger = logging.getLogger(__name__)

try:
    from Queue import *
except ImportError:
    from queue import *

from functools import partial

from . import Utils
from .CNC import CMDPAT, CNC, LASER_TOOL_NUMBER, PARENPAT, SEMIPAT, ZPROBE_TOOL_NUMBER
from .machine.adaptive_monitor import AdaptiveMonitor, Sample
from .machine.receive_health import ReceiveHealth
from .machine.sensor_run_recording import RunEvidence, parse_numeric_fields
from .machine.slot_inventory import SlotInventory
from .machine.telemetry_log import TelemetryLog
from .protocols import MessageKind, ProtocolSession
from .USBStream import USBStream
from .WIFIStream import WIFIStream

try:
    from kivy.app import App
    from kivy.clock import Clock
except ImportError:
    # Fallback if kivy is not available (e.g., during testing)
    Clock = None
    App = None

STREAM_POLL = 0.2  # s
DIAGNOSE_POLL = 0.5  # s
BACKGROUND_DIAGNOSE_POLL = 2.0  # bounded, idle protocol only
MAX_EVIDENCE_LOG_BYTES = 64 * 1024 * 1024
STATUS_REACQUIRE_TIMEOUT = 5.0  # bounded post-transfer wait for actual status
RX_BUFFER_SIZE = 128

GPAT = re.compile(r"[A-Za-z]\s*[-+]?\d+.*")
FEEDPAT = re.compile(r"^(.*)[fF](\d+\.?\d+)(.*)$")

STATUSPAT = re.compile(
    r"^<(\w*?),MPos:([+\-]?\d*\.\d*),([+\-]?\d*\.\d*),([+\-]?\d*\.\d*),WPos:([+\-]?\d*\.\d*),([+\-]?\d*\.\d*),([+\-]?\d*\.\d*),?(.*)>$"
)
POSPAT = re.compile(r"^\[(...):([+\-]?\d*\.\d*),([+\-]?\d*\.\d*),([+\-]?\d*\.\d*):?(\d*)\]$")
TLOPAT = re.compile(r"^\[(...):([+\-]?\d*\.\d*)\]$")
DOLLARPAT = re.compile(r"^\[G\d* .*\]$")
SPLITPAT = re.compile(r"[:,]")
VARPAT = re.compile(r"^\$(\d+)=(\d*\.?\d*) *\(?.*")


WIKI = "https://github.com/vlachoudis/bCNC/wiki"

CONNECTED = "Wait"
NOT_CONNECTED = "N/A"

STATECOLORDEF = (155 / 255, 155 / 255, 155 / 255, 1)  # Default color for unknown types or not connected
STATECOLOR = {
    "Idle": (52 / 255, 152 / 255, 219 / 255, 1),
    "Run": (34 / 255, 153 / 255, 84 / 255, 1),
    "Tool": (34 / 255, 153 / 255, 84 / 255, 1),
    "Alarm": (231 / 255, 76 / 255, 60 / 255, 1),
    "Home": (247 / 255, 220 / 255, 111 / 255, 1),
    "Hold": (34 / 255, 153 / 255, 84 / 255, 1),
    "Wait": (247 / 255, 220 / 255, 111 / 255, 1),
    "Disable": (100 / 255, 100 / 255, 100 / 255, 1),
    "Sleep": (220 / 255, 220 / 255, 220 / 255, 1),
    "Pause": (52 / 255, 152 / 255, 219 / 255, 1),
    NOT_CONNECTED: (155 / 255, 155 / 255, 155 / 255, 1),
}

LOAD_DIR = 1
LOAD_RM = 2
LOAD_MV = 3
LOAD_MKDIR = 4
LOAD_WIFI = 7
LOAD_CONN_WIFI = 8

SEND_FILE = 1

CONN_USB = 0
CONN_WIFI = 1


# ==============================================================================
# Controller class
# ==============================================================================
class Controller:
    MSG_NORMAL = 0
    MSG_ERROR = 1
    MSG_INTERIOR = 2

    JOG_MODE_STEP = 0
    JOG_MODE_CONTINUOUS = 1

    _evidence_global_lock = threading.RLock()
    _instances = weakref.WeakSet()
    usb_stream = None
    wifi_stream = None
    stream = None
    modem = None
    connection_type = CONN_WIFI
    # Set by open(). Declared here because updateStatus and the camera probe
    # read it before any connection has been made, and an AttributeError there
    # is swallowed by a bare except, silently killing the rest of the update.
    connection_address = None

    def __init__(self, cnc, callback, log_sent_receive=False):
        self.stop = threading.Event()
        self._adaptive_lock = threading.RLock()
        self.observed_pose = None
        self.adaptive_monitor = AdaptiveMonitor()
        from .machine.run_recording import RunRecording

        self.run_recording = RunRecording()
        self.adaptive_log_path = None
        self.sensor_log_path = None
        self._adaptive_log = None
        from .machine.telemetry_recovery import TelemetryRecovery

        self._telemetry_recovery = TelemetryRecovery()
        self._telemetry_logging_closed = False
        self._telemetry_prior_lost = 0
        self._adaptive_log_failed = False
        self._evidence_writer = None
        self._recording_last_error = None
        self._recovery_pending_token = 0
        self._recovery_scheduled = None
        self._recovery_pending_active = False
        self._recovery_cancel_event = threading.Event()
        self._recovery_signal_lock = threading.Lock()
        self._recovery_external_requests = 0
        self._recovery_queue_dirty = False
        self._recovery_disposal_nonce = None
        self._recovery_disposal_ack = False
        self._recovery_nonce_counter = int.from_bytes(os.urandom(4), "big") or 1
        self.run_evidence = RunEvidence()
        self.measurement_command_callback = None
        self.measurement_context_provider = None
        self._last_previous_fault_dump_requested = None
        self._evidence_writes_enabled = True
        self._evidence_arrival_override = None
        self._last_fault_dump_requested = None
        self._fault_dump_pending = False
        self._recovery_verification = None
        self._recovery_line = None
        self._recovery_assessment = None
        self.usb_stream = USBStream(log_sent_receive)
        self.wifi_stream = WIFIStream(log_sent_receive)

        # Reconnection properties
        self.reconnect_enabled = True
        self.reconnect_wait_time = 10
        self.reconnect_attempts = 3
        self.reconnect_countdown = 0
        self.reconnect_timer = None
        self.reconnect_callback = None
        self.cancel_reconnect_callback = None
        self._manual_disconnect = False

        # Global variables
        self.history = []
        self._historyPos = None

        # CNC.loadConfig(Utils.config)
        self.cnc = cnc

        self.execCallback = callback

        self.log = Queue()  # Log queue returned from GRBL
        self.queue = Queue()  # Command queue to be send to GRBL
        self.load_buffer = Queue()
        self.load_buffer_size = 0
        self.total_buffer_size = 0

        self.loadNUM = 0
        self.loadEOF = False
        self.loadERR = False
        self.loadCANCEL = False
        self.loadCANCELSENT = False

        self.sendNUM = 0
        self.sendEOF = False
        self.sendCANCEL = False

        self.thread = None
        self._receive_threads = weakref.WeakSet()

        self.posUpdate = False  # Update position
        self.diagnoseUpdate = False
        self._probeUpdate = False  # Update probe
        self._gUpdate = False  # Update $G
        self._update = None  # Generic update

        self.cleanAfter = False
        self._runLines = 0
        self._quit = 0  # Quit counter to exit program
        self._stop = False  # Raise to stop current run
        self._pause = False  # machine is on Hold
        self._alarm = True  # Display alarm message if true

        self._baud_upgrade_attempted = False
        self._baud_switch_in_progress = False
        self._refresh_heartbeat = False
        self._connection_generation = 0
        self._capability_observations = {}
        self.slot_inventory = SlotInventory()
        self._connection_started_at = None
        self._last_status_received_at = None
        self._receive_health = ReceiveHealth(0, time.monotonic())
        self._receive_losses = deque(maxlen=8)
        self._status_reacquire_started_at = None
        self._status_reacquire_deadline = None
        self._status_poll_requested = False
        # True from open() start until streamIO is running (hides half-open links from heartbeat).
        self._connecting = False
        # Epoch seconds; while time.time() < this, heartbeat will not drop the link.
        # Used after USB DTR reset while the machine is still booting.
        self._heartbeat_grace_until = 0.0
        # True while streamIO is idle (paused / no stream); used to sync baud switch.
        self._stream_io_parked = True

        self._msg = None
        self._sumcline = 0
        self._lastFeed = 0
        self._newFeed = 0

        self._onStart = ""
        self._onStop = ""

        self.paused = False
        self.pausing = False

        self.diagnosing = False
        self._diagnose_requested_at = None

        self.is_community_firmware = False

        # Connection-scoped comms protocol (detect on open; follows M485 switches)
        self.comms = ProtocolSession(on_change=self._on_comms_protocol_changed)

        # Jog related variables
        self.jog_mode = Controller.JOG_MODE_STEP
        self.jog_speed = 10000  # mm/min. A value of 0 here would suggest to use last used feed
        self.continuous_jog_active = False
        # True after Ctrl+Y until firmware acks (^Y) — suppresses keepalives without
        # allowing a new $J -c to start before the previous jog has stopped.
        self._continuous_jog_stopping = False
        self._instances.add(self)

    @property
    def protocol_ready(self):
        return self.comms.ready

    def _on_comms_protocol_changed(self, name, uses_framed_transfer):
        """Keep transports' file-transfer mode aligned with the comms session."""
        if self.usb_stream is not None:
            self.usb_stream.uses_framed_transfer = uses_framed_transfer
        if self.wifi_stream is not None:
            self.wifi_stream.uses_framed_transfer = uses_framed_transfer
        if self.comms.ready:
            self.log.put((self.MSG_NORMAL, f"Using {name} communication protocol"))

    # ----------------------------------------------------------------------
    def quit(self, event=None):
        pass

    # ----------------------------------------------------------------------
    def loadConfig(self):
        pass

    # ----------------------------------------------------------------------
    def saveConfig(self):
        pass

    # ----------------------------------------------------------------------
    # Execute a line as gcode if pattern matches
    # @return True on success
    # False otherwise
    # ----------------------------------------------------------------------
    def executeGcode(self, line):
        if isinstance(line, tuple) or line[0] in ("$", "!", "~", "?", "(", "@") or GPAT.match(line):
            self.sendGCode(line)
            return True
        return False

    # ----------------------------------------------------------------------
    # Execute a single command
    # ----------------------------------------------------------------------
    def _command_is_query(self, line):
        text = line.decode(errors="replace") if isinstance(line, bytes) else str(line)
        queries = {
            "time",
            "ftype",
            "diagnose",
            "version",
            "model",
            "ls",
            "cat",
            "md5",
            "md5sum",
            "m889",
            "m964",
            "evidence",
            "adaptive",
        }
        return all(part.split()[0].lower() in queries for part in text.splitlines() if part.strip())

    def _signal_external_control(self):
        # Signal before taking the transport lock. An operator stop must prevent
        # the next recovery command even while the current write is in flight.
        with self._recovery_signal_lock:
            self._recovery_external_requests += 1
            self._recovery_cancel_event.set()

    def _finish_external_control(self):
        with self._recovery_signal_lock:
            self._recovery_external_requests -= 1

    def executeCommand(self, line, *, recovery_token=None):
        external = recovery_token is None and not self._command_is_query(line)
        if external:
            self._signal_external_control()
        try:
            with self._adaptive_lock:
                if recovery_token is not None:
                    if (
                        recovery_token != self._recovery_pending_token
                        or not self._recovery_pending_active
                        or self._recovery_cancel_event.is_set()
                        or self.stop.is_set()
                    ):
                        return False
                elif external:
                    self._cancel_pending_recovery("operator command")
                if self._recovery_disposal_nonce is not None and not self._command_is_query(line):
                    text = line.decode(errors="replace") if isinstance(line, bytes) else str(line)
                    if any(
                        part.split()[0].lower() not in {"abort", "suspend", "recovery", "$x"}
                        for part in text.splitlines()
                        if part.strip()
                    ):
                        self.log.put(
                            (
                                self.MSG_ERROR,
                                "Command blocked: recovery buffer disposal awaits matching firmware acknowledgement and fresh Idle status",
                            )
                        )
                        return False
                return self._execute_command_unlocked(line)
        finally:
            if external:
                self._finish_external_control()

    def _execute_command_unlocked(self, line):
        # if self.sio_status != False or self.sio_diagnose != False:      #wait for the ? or * command
        #    time.sleep(0.5)
        if isinstance(line, str) and line.strip().lower().startswith("recovery"):
            return self.recoveryCommand(line.strip())
        if isinstance(line, str) and line.strip().lower().startswith("evidence"):
            return self.evidenceCommand(line.strip())
        if self.status_reacquisition_pending:
            text = line.decode(errors="replace") if isinstance(line, bytes) else str(line)
            # During this short handoff only explicit queries and stop requests
            # may pass. Inspect every line; a query followed by motion is not a
            # query. Do not infer readiness from the old Idle state.
            queries = {"time", "ftype", "diagnose", "version", "ls", "cat", "md5", "m889", "abort", "suspend"}
            if any(part.split()[0].lower() not in queries for part in text.splitlines() if part.strip()):
                self.log.put((self.MSG_ERROR, "Command blocked: awaiting fresh post-transfer machine status"))
                return False
        if isinstance(line, str) and line.strip().lower().startswith("adaptive"):
            return self.adaptiveCommand(line.strip())
        if self.stream and line:
            try:
                if isinstance(line, str) and not line.endswith("\n"):
                    line += "\n"
                # Soft `reset` over USB leaves the board powered (zombie state).
                if isinstance(line, str) and self.connection_type == CONN_USB and line.lower().startswith("reset"):
                    self._notify_usb_reset_blocked()
                    return None
                payload = line.encode() if isinstance(line, str) else line
                self.stream.send(self.comms.encode_command(payload))
                if self.measurement_command_callback:
                    try:
                        self.measurement_command_callback(payload.decode(errors="replace"))
                    except Exception as error:
                        self.log.put(
                            (self.MSG_ERROR, "Command sent; measurement evidence callback failed: " + str(error))
                        )
                if self.execCallback:
                    display = line if isinstance(line, str) else line.decode(errors="ignore")
                    # Strip ".lz" suffix for display
                    if display.endswith(".lz\n"):
                        new_line = display[:-4] + "\n"
                    else:
                        new_line = display
                    self.execCallback(new_line)
                return True
            except Exception:
                self.log.put((Controller.MSG_ERROR, str(sys.exc_info()[1])))
        return False

    def query_slot_inventory(self):
        """Explicit bounded coordinate readback; never changes pockets/tools."""
        from .machine.capabilities import CarveraAdapter, FirmwareIdentity, carvera_capabilities

        now = time.monotonic()
        with self._adaptive_lock:
            self.slot_inventory.expire(self._connection_generation, now)
            pose = self.observed_pose
            if not self.stream or self.paused or self.status_reacquisition_pending:
                raise ValueError("Connect with active status reception before querying pockets")
            if pose is None or not pose.fresh(now) or pose.state != "Idle":
                raise ValueError("A fresh Idle packet is required for slot readback")
            observations = self._capability_observations
            firmware = observations.get("firmware", "")
            capabilities = carvera_capabilities(
                "observed",
                observations.get("model", ""),
                FirmwareIdentity("community" if "c" in firmware.lower() else "vendor", firmware),
                pose.timestamp,
                has_atc=observations.get("has_atc"),
            )
            capabilities.require("atc", now)
            plan = CarveraAdapter(capabilities).query_slots(now)
            self.slot_inventory.begin(
                self._connection_generation,
                now,
                {
                    "model": observations.get("model", ""),
                    "firmware": firmware,
                    "protocol": self.comms.name,
                    "address": self.connection_address or "",
                },
            )
            if not self.executeCommand(plan.commands[0]):
                self.slot_inventory.fail("Slot query transport failed; no receipt")
                raise ValueError(self.slot_inventory.error)

    def _notify_usb_reset_blocked(self):
        if App is None or Clock is None:
            return
        app = App.get_running_app()
        if app is None or getattr(app, "root", None) is None:
            return
        root = app.root
        if hasattr(root, "show_usb_reset_blocked_popup"):
            Clock.schedule_once(lambda dt: root.show_usb_reset_blocked_popup(), 0)

    def executeRealtime(self, char):
        """Send a single-byte realtime control through the active protocol."""
        self.executeRealtimeSequence(char)

    def executeRealtimeSequence(self, *chars):
        external = any((char[0] if isinstance(char, (bytes, bytearray)) else char) != ord("?") for char in chars)
        if external:
            self._signal_external_control()
        try:
            with self._adaptive_lock:
                if external:
                    self._cancel_pending_recovery("realtime operator control")
                if self._recovery_disposal_nonce is not None and any(
                    (char[0] if isinstance(char, (bytes, bytearray)) else char) not in (ord("?"), ord("!"), 0x18)
                    for char in chars
                ):
                    self.log.put((self.MSG_ERROR, "Realtime motion blocked: recovery buffer disposal is unconfirmed"))
                    return False
                return self._execute_realtime_unlocked(*chars)
        finally:
            if external:
                self._finish_external_control()

    def _execute_realtime_unlocked(self, *chars):
        """Send one or more realtime bytes in a single write.

        Smoothie continuous-jog keepalive is the digram ``?1``. Sending ``?`` and
        ``1`` as separate writes races with other commands and leaves orphaned
        ``1`` bytes in the firmware command buffer (seen as ``111…$J …``).
        """
        if not self.stream or not chars:
            return None
        if self.status_reacquisition_pending and any(
            (char[0] if isinstance(char, (bytes, bytearray)) else char) in (ord("~"), ord("1"), 0x1A) for char in chars
        ):
            self.log.put((self.MSG_ERROR, "Motion resume blocked: awaiting fresh post-transfer machine status"))
            return False
        try:
            payload = bytearray()
            status_poll = False
            health = self._receive_health
            for char in chars:
                if isinstance(char, (bytes, bytearray)):
                    char = char[0]
                payload.extend(self.comms.encode_realtime(int(char)))
                status_poll = status_poll or int(char) == ord("?")
            self.stream.send(bytes(payload))
            if status_poll:
                health.poll(time.monotonic())
        except Exception:
            self.log.put((Controller.MSG_ERROR, str(sys.exc_info()[1])))

    def executeFileCommand(self, line):
        self._signal_external_control()
        try:
            with self._adaptive_lock:
                self._cancel_pending_recovery("file transfer")
                if self._recovery_disposal_nonce is not None:
                    self.log.put((self.MSG_ERROR, "File transfer blocked: recovery buffer disposal is unconfirmed"))
                    return False
                return self._execute_file_command_unlocked(line)
        finally:
            self._finish_external_control()

    def _execute_file_command_unlocked(self, line):
        """Send an upload/download initiation command through the active protocol."""
        if self.stream and line:
            try:
                if isinstance(line, str) and not line.endswith("\n"):
                    line += "\n"
                payload = line.encode() if isinstance(line, str) else line
                self.stream.send(self.comms.encode_file_command(payload))
                if self.execCallback:
                    display = line if isinstance(line, str) else line.decode(errors="ignore")
                    if display.endswith(".lz\n"):
                        new_line = display[:-4] + "\n"
                    else:
                        new_line = display
                    self.execCallback(new_line)
            except Exception:
                self.log.put((Controller.MSG_ERROR, str(sys.exc_info()[1])))

    # ----------------------------------------------------------------------
    def autoCommand(
        self,
        margin=False,
        zprobe=False,
        zprobe_abs=False,
        leveling=False,
        goto_origin=False,
        z_probe_offset_x=0,
        z_probe_offset_y=0,
        i=3,
        j=3,
        h=5,
        buffer=False,
        auto_level_offsets=None,
        upcoming_tool=0,
    ):
        if not (margin or zprobe or leveling or goto_origin):
            return
        if auto_level_offsets is None:
            auto_level_offsets = [0, 0, 0, 0]
        if abs(CNC.vars["xmin"]) > CNC.vars["worksize_x"] or abs(CNC.vars["ymin"]) > CNC.vars["worksize_y"]:
            return
        cmd = "M495 X%gY%g" % (CNC.vars["xmin"], CNC.vars["ymin"])
        if margin:
            cmd = cmd + "C%gD%g" % (CNC.vars["xmax"], CNC.vars["ymax"])
            if buffer:
                cmd = "buffer " + cmd
            self.executeCommand(
                cmd
            )  # run margin command. Has to be two seperate commands to offset the start of the autolevel process
        cmd = "M495 X%gY%g" % (
            CNC.vars["xmin"] + auto_level_offsets[0],
            CNC.vars["ymin"] + auto_level_offsets[2],
        )  # reinitialize command with any autolevel offsets
        if zprobe:
            if zprobe_abs:
                cmd = "M495 X%gY%g" % (CNC.vars["xmin"], CNC.vars["ymin"])  # reset command for 4th axis
                cmd = cmd + "O0"
            else:
                cmd = cmd + "O%gF%g" % (z_probe_offset_x, z_probe_offset_y)
        if leveling:
            cmd = cmd + "A%gB%gI%dJ%dH%d" % (
                CNC.vars["xmax"] - (CNC.vars["xmin"] + auto_level_offsets[1] + auto_level_offsets[0]),
                CNC.vars["ymax"] - (CNC.vars["ymin"] + auto_level_offsets[3] + auto_level_offsets[2]),
                i,
                j,
                h,
            )
        if goto_origin:
            cmd = cmd + "P1"
            # Include the first tool number so firmware can do tool change/TLO before going to origin
            if upcoming_tool > 0:
                cmd = cmd + "T%d" % upcoming_tool
        cmd = cmd + "\n"
        if buffer:
            cmd = "buffer " + cmd
        self.executeCommand(cmd)

    def xyzProbe(self, height=9.0, diameter=3.175, buffer=False):
        cmd = "M495.3 H%g D%g" % (height, diameter)
        if buffer:
            cmd = "buffer " + cmd
        self.executeCommand(cmd)

    def pairWP(self):
        self.executeCommand("M471")

    def syncTime(self, *args):
        self.executeCommand("time " + str(Utils.local_unix_time()))

    def queryTime(self, *args):
        self.executeCommand("time")

    def queryVersion(self, *args):
        self.executeCommand("version")

    def queryModel(self, *args):
        self.executeCommand("model")

    def queryFtype(self, *args):
        self.executeCommand("ftype")

    # # ----------------------------------------------------------------------
    # def zProbeCommand(self, c=0, d=0, buffer=False):
    #     cmd = "M494 X%gY%gC%gD%g\n" % (CNC.vars['xmin'], CNC.vars['ymin'], c, d)
    #     if buffer:
    #         cmd = "buffer " + cmd
    #     self.executeCommand(cmd)

    # def autoLevelCommand(self, i=3, j=3, buffer=False):
    #     cmd = "M495 X%gY%gA%gB%gI%dJ%d\n" % (CNC.vars['xmin'], CNC.vars['ymin'], CNC.vars['xmax'] - CNC.vars['xmin'], CNC.vars['ymax'] - CNC.vars['ymin'], i, j)
    #     if buffer:
    #         cmd = "buffer " + cmd
    #     self.executeCommand(cmd)

    # def probeLevelCommand(self, i=3, j=3, buffer=False):
    #     cmd = "M496 X%gY%gA%gB%gI%dJ%d\n" % (CNC.vars['xmin'], CNC.vars['ymin'], CNC.vars['xmax'] - CNC.vars['xmin'], CNC.vars['ymax'] - CNC.vars['ymin'], i, j)
    #     if buffer:
    #         cmd = "buffer " + cmd
    #     self.executeCommand(cmd)

    def gotoClearance(self, buffer=False):
        cmd = "M496.1\n"
        if buffer:
            cmd = "buffer " + cmd
        self.executeCommand(cmd)

    def gotoWorkOrigin(self, buffer=False):
        cmd = "M496.2\n"
        if buffer:
            cmd = "buffer " + cmd
        self.executeCommand(cmd)

    def gotoAnchor1(self, buffer=False):
        cmd = "M496.3\n"
        if buffer:
            cmd = "buffer " + cmd
        self.executeCommand(cmd)

    def gotoAnchor2(self, buffer=False):
        cmd = "M496.4\n"
        if buffer:
            cmd = "buffer " + cmd
        self.executeCommand(cmd)

    def gotoPathOrigin(self, buffer=False):
        if abs(CNC.vars["xmin"]) <= CNC.vars["worksize_x"] and abs(CNC.vars["ymin"]) <= CNC.vars["worksize_y"]:
            cmd = "M496.5 X%gY%g\n" % (CNC.vars["xmin"], CNC.vars["ymin"])
            if buffer:
                cmd = "buffer " + cmd
            self.executeCommand(cmd)

    def gotoPosition(self, position, buffer=False):
        """Legacy method to route to appropriate goto method based on position string"""
        if position is None:
            return
        if position == "Clearance":
            self.gotoClearance(buffer)
        elif position == "Work Origin":
            self.gotoWorkOrigin(buffer)
        elif position == "Anchor1":
            self.gotoAnchor1(buffer)
        elif position == "Anchor2":
            self.gotoAnchor2(buffer)
        elif position == "Path Origin":
            self.gotoPathOrigin(buffer)

    def reset(self):
        self.executeCommand("reset\n")

    def change(self):
        app = App.get_running_app()
        if app.has_atc:
            self.executeCommand("M490.4\n")
        else:
            self.executeCommand("M490.2\n")

    def setFeedScale(self, scale):
        app = App.get_running_app()
        if (
            app.is_community_firmware and app.fw_version_digitized >= Utils.digitize_v("2.1.0")
        ) and app.root.instantFSoverride:
            self.executeCommand("$F S%d\n" % (scale))
            return
        self.executeCommand("M220 S%d\n" % (scale))

    def setLaserScale(self, scale):
        self.executeCommand("M325 S%d\n" % (scale))

    def setSpindleScale(self, scale):
        app = App.get_running_app()
        if (
            app.is_community_firmware and app.fw_version_digitized >= Utils.digitize_v("2.1.0")
        ) and app.root.instantFSoverride:
            self.executeCommand("$O S%d\n" % (scale))
            return
        self.executeCommand("M223 S%d\n" % (scale))

    def clearAutoLeveling(self):
        self.executeCommand("M370\n")

    def setSpindleSwitch(self, switch, rpm=None):
        if switch and rpm is not None:
            cmd = f"M3 S{int(rpm)}\n"
        elif switch and rpm is None:
            cmd = "M3\n"
        else:
            cmd = "M5\n"
        self.executeCommand(cmd)

    def setVacuumPower(self, power=0):
        if power > 0:
            self.executeCommand("M801 S%d\n" % (power))
        else:
            self.executeCommand("M802\n")

    def setSpindlefanPower(self, power=0):
        if power > 0:
            self.executeCommand("M811 S%d\n" % (power))
        else:
            self.executeCommand("M812\n")

    def setLaserPower(self, power=0):
        if power > 0:
            self.executeCommand("M3 S%g\n" % (power * 1.0 / 100))
        else:
            self.executeCommand("M5\n")

    def setLightSwitch(self, switch):
        if switch:
            self.executeCommand("M821\n")
        else:
            self.executeCommand("M822\n")

    def setExternalControl(self, pwm=100):
        if pwm > 0:
            self.executeCommand("M851 S%g\n" % (pwm))
        else:
            self.executeCommand("M852\n")

    def setToolSensorSwitch(self, switch):
        if switch:
            self.executeCommand("M831\n")
        else:
            self.executeCommand("M832\n")

    def setAirSwitch(self, switch):
        if switch:
            self.executeCommand("M7\n")
        else:
            self.executeCommand("M9\n")

    def setPWChargeSwitch(self, switch):
        if switch:
            self.executeCommand("M841\n")
        else:
            self.executeCommand("M842\n")

    def setVacuumMode(self, mode):
        if mode:
            self.executeCommand("M331\n")
        else:
            self.executeCommand("M332\n")

    def setExtOutMode(self, mode):
        if mode:
            self.executeCommand("M331.3\n")
        else:
            self.executeCommand("M332.3\n")

    def setLaserMode(self, mode):
        if mode:
            self.executeCommand("M321\n")
        else:
            self.executeCommand("M322\n")

    def setLaserTest(self, test):
        if test:
            self.executeCommand("M323\n")
        else:
            self.executeCommand("M324\n")

    def setConfigValue(self, key, value):
        if key and value:
            self.executeCommand("config-set sd %s %s\n" % (key, value))

    def dropToolCommand(self):
        self.executeCommand("M6T-1\n")

    def calibrateToolCommand(self):
        self.executeCommand("M491\n")

    def calibrate_tool_advanced_command(self, repeat_count=1, x_offset=0.0, y_offset=0.0):
        parts = ["M491"]
        if x_offset != 0:
            parts.append("X%g" % x_offset)
        if y_offset != 0:
            parts.append("Y%g" % y_offset)
        if repeat_count != 1:
            parts.append("R%d" % repeat_count)
        self.executeCommand(" ".join(parts) + "\n")

    def clampToolCommand(self):
        self.executeCommand("M490.1\n")

    def unclampToolCommand(self):
        self.executeCommand("M490.2\n")

    def change_tool_command(self, tool):
        if tool == "e":
            self.executeCommand("M6T%d\n" % ZPROBE_TOOL_NUMBER)
        elif tool == "r":
            self.executeCommand("M6T%d\n" % LASER_TOOL_NUMBER)
        elif tool == "m":
            # custom tool number
            pass
        else:
            self.executeCommand("M6T%s\n" % tool)

    def set_tool_command(self, tool):
        if tool == "e":
            self.executeCommand("M493.2T%d\n" % ZPROBE_TOOL_NUMBER)
        elif tool == "r":
            self.executeCommand("M493.2T%d\n" % LASER_TOOL_NUMBER)
        elif tool == "m":
            # custom tool number
            pass
        elif tool == "y":
            self.executeCommand("M493.2T-1\n")
        else:
            self.executeCommand("M493.2T%s\n" % tool)

    def bufferChangeToolCommand(self, tool):
        self.executeCommand("buffer M6T%s\n" % tool)

    # ------------------------------------------------------------------------------
    # escape special characters
    # ------------------------------------------------------------------------------
    def escape(self, value):
        """Escape special characters for protocol transmission"""
        return value.replace("?", "\x02").replace("&", "\x03").replace("!", "\x04").replace("~", "\x05")

    def lsCommand(self, ls_dir):
        ls_command = "ls -e -s %s\n" % ls_dir.replace(" ", "\x01")
        if "\\" in ls_dir:
            ls_command = "ls -e -s %s\n" % "/".join(ls_dir.split("\\")).replace(" ", "\x01")
        self.executeCommand(self.escape(ls_command))

    def catCommand(self, filename):
        cat_command = "cat %s -e\n" % filename.replace(" ", "\x01")
        if "\\" in filename:
            cat_command = "cat %s -e\n" % "/".join(filename.split("\\")).replace(" ", "\x01")
        self.executeCommand(self.escape(cat_command))

    def rmCommand(self, filename):
        rm_command = "rm %s -e\n" % filename.replace(" ", "\x01")
        if "\\" in filename:
            rm_command = "rm %s -e\n" % "/".join(filename.split("\\")).replace(" ", "\x01")
        self.executeCommand(self.escape(rm_command))

    def mvCommand(self, file, newfile):
        mv_command = "mv %s %s -e\n" % (file.replace(" ", "\x01"), newfile.replace(" ", "\x01"))
        if "\\" in file or "\\" in newfile:
            mv_command = "mv %s %s -e\n" % (
                "/".join(file.split("\\")).replace(" ", "\x01"),
                "/".join(newfile.split("\\")).replace(" ", "\x01"),
            )
        self.executeCommand(self.escape(mv_command))

    def mkdirCommand(self, dirname):
        mkdir_command = "mkdir %s -e\n" % dirname.replace(" ", "\x01")
        if "\\" in dirname:
            mkdir_command = "mkdir %s -e\n" % "/".join(dirname.split("\\")).replace(" ", "\x01")
        self.executeCommand(self.escape(mkdir_command))

    def md5Command(self, filename):
        md5_command = "md5sum %s -e\n" % filename.replace(" ", "\x01")
        if "\\" in filename:
            md5_command = "md5sum %s -e\n" % "/".join(filename.split("\\")).replace(" ", "\x01")
        self.executeCommand(self.escape(md5_command))

    def loadWiFiCommand(self):
        self.executeCommand("wlan -e\n")

    def disconnectWiFiCommand(self):
        self.executeCommand("wlan -d disconnect\n")

    def connectWiFiCommand(self, ssid, password):
        wifi_command = "wlan %s %s -e\n" % (ssid.replace(" ", "\x01"), password.replace(" ", "\x01"))
        self.executeCommand(self.escape(wifi_command))

    def loadConfigCommand(self):
        self.executeCommand("config-get-all -e\n")

    def restoreConfigCommand(self):
        self.executeCommand("config-restore\n")

    def defaultConfigCommand(self):
        self.executeCommand("config-default\n")

    def uploadCommand(self, filename):
        self._program_request(filename, "upload requested")
        upload_command = "upload %s\n" % filename.replace(" ", "\x01")
        if "\\" in filename:
            upload_command = "upload %s\n" % "/".join(filename.split("\\")).replace(" ", "\x01")
        self.executeFileCommand(self.escape(upload_command))

    def downloadCommand(self, filename):
        download_command = "download %s\n" % filename.replace(" ", "\x01")
        if "\\" in filename:
            download_command = "download %s\n" % "/".join(filename.split("\\")).replace(" ", "\x01")
        self.executeFileCommand(self.escape(download_command))

    def suspendCommand(self):
        self.executeCommand("suspend\n")

    def resumeCommand(self):
        self.executeCommand("resume\n")

    def playCommand(self, filename, has_ocodes=False):
        self._program_request(filename, "play requested")
        flag = " -O" if has_ocodes else ""
        play_command = "play %s%s\n" % (filename.replace(" ", "\x01"), flag)
        if "\\" in filename:
            play_command = "play %s%s\n" % ("/".join(filename.split("\\")).replace(" ", "\x01"), flag)
        self.executeCommand(self.escape(play_command))

    def _binary_find_left(self, array, key):
        """
        Binary search to find the leftmost position where key could be inserted.
        Returns the index of the last element less than key, or -1 if key is smaller than all elements.
        """
        length = len(array)
        ans = length
        l = 0
        r = length - 1
        while l <= r:
            mid = (l + r) >> 1
            if array[mid] >= key:
                ans = mid
                r = mid - 1
            else:
                l = mid + 1
        return ans - 1

    def _get_line_position_from_gcode_viewer(self, line_number):
        """
        Get the X/Y/Z/A position for a specific line number from the loaded gcode file using GcodeViewer.

        Args:
            line_number: The line number (1-based) to get position for

        Returns:
            Tuple of (x, y, z, a) where x, y, z are floats and a is float or None.
            Returns (None, None, None, None) if position cannot be determined.
        """
        if App is None:
            return (None, None, None, None)

        try:
            app = App.get_running_app()
            if not app or not hasattr(app.root, "gcode_viewer") or not app.root.gcode_viewer:
                return (None, None, None, None)

            gcode_viewer = app.root.gcode_viewer

            # Check if gcode_viewer has the necessary data
            if not hasattr(gcode_viewer, "raw_linenumbers") or not gcode_viewer.raw_linenumbers:
                return (None, None, None, None)

            # Convert line_number to float for comparison (raw_linenumbers stores floats)
            line_num_float = float(line_number)

            # Find the vertex index for this line number using binary search
            left_pos = self._binary_find_left(gcode_viewer.raw_linenumbers, line_num_float)

            # Find the rightmost position with the same line number
            right_pos = left_pos
            while (
                right_pos < len(gcode_viewer.raw_linenumbers) - 1
                and gcode_viewer.raw_linenumbers[right_pos + 1] == line_num_float
            ):
                right_pos = right_pos + 1

            # Use the rightmost position (end of line) to get the final position
            vertex_idx = right_pos

            # Validate vertex index
            if vertex_idx < 0 or vertex_idx >= len(gcode_viewer.raw_linenumbers):
                return (None, None, None, None)

            # Get position from meshmanager (use raw_positions for unrotated G-code coordinates)
            if hasattr(gcode_viewer, "meshmanager") and gcode_viewer.meshmanager:
                # Use raw_positions array for unrotated G-code coordinates
                if hasattr(gcode_viewer.meshmanager, "raw_positions") and gcode_viewer.meshmanager.raw_positions:
                    pos_idx = vertex_idx * 3
                    if pos_idx + 2 < len(gcode_viewer.meshmanager.raw_positions):
                        x = gcode_viewer.meshmanager.raw_positions[pos_idx]
                        y = gcode_viewer.meshmanager.raw_positions[pos_idx + 1]
                        z = gcode_viewer.meshmanager.raw_positions[pos_idx + 2]

                        # Get angle if 4-axis
                        a = None
                        if (
                            hasattr(gcode_viewer.meshmanager, "angles_of_vertices")
                            and gcode_viewer.meshmanager.angles_of_vertices
                        ):
                            if vertex_idx < len(gcode_viewer.meshmanager.angles_of_vertices):
                                a = gcode_viewer.meshmanager.angles_of_vertices[vertex_idx]

                        return (x, y, z, a)
            else:
                # Fallback: use raw_positions array directly from gcode_viewer
                if hasattr(gcode_viewer, "raw_positions") and gcode_viewer.raw_positions:
                    pos_idx = vertex_idx * 3
                    if pos_idx + 2 < len(gcode_viewer.raw_positions):
                        x = gcode_viewer.raw_positions[pos_idx]
                        y = gcode_viewer.raw_positions[pos_idx + 1]
                        z = gcode_viewer.raw_positions[pos_idx + 2]

                        # Get angle if 4-axis
                        a = None
                        if hasattr(gcode_viewer, "angles_of_vertices") and gcode_viewer.angles_of_vertices:
                            if vertex_idx < len(gcode_viewer.angles_of_vertices):
                                a = gcode_viewer.angles_of_vertices[vertex_idx]

                        return (x, y, z, a)

            return (None, None, None, None)

        except Exception as e:
            logger.warning(f"Error getting line position from gcode_viewer for line {line_number}: {e}")
            return (None, None, None, None)

    def _find_m3_spindle_speed(self, lines, start_line):
        """
        Search backwards from start_line to find M3 commands and extract S (spindle speed) parameter.
        First checks the most recent M3 command, then searches backwards if no S parameter found.

        Args:
            lines: Gcode file lines (1-based line numbers index into this list)
            start_line: Line number to search backwards from (1-based)

        Returns:
            Spindle speed value as float, or None if not found
        """
        if not lines:
            return None

        try:
            # Ensure start_line is an integer
            try:
                start_line = int(start_line)
            except (ValueError, TypeError):
                logger.warning(f"Invalid start_line value: {start_line}")
                return None

            if start_line < 1 or start_line > len(lines):
                return None

            # First, find the most recent M3 command and check if it has S parameter.
            # Token matching normalizes zero-padded forms such as M03 without
            # confusing other M-codes such as M30.
            most_recent_m3_line = None
            for i in range(start_line - 2, -1, -1):
                has_m3, spindle_speed = self._m3_spindle_speed_from_line(lines[i])
                if has_m3:
                    most_recent_m3_line = i
                    if spindle_speed is not None:
                        return spindle_speed
                    # Found M3 but no S parameter, continue searching backwards
                    break

            # If we found M3 but no S parameter, search backwards for previous M3 with S
            if most_recent_m3_line is not None:
                for i in range(most_recent_m3_line - 1, -1, -1):
                    has_m3, spindle_speed = self._m3_spindle_speed_from_line(lines[i])
                    if has_m3 and spindle_speed is not None:
                        return spindle_speed

            return None

        except Exception as e:
            logger.warning(f"Error finding M3 spindle speed before line {start_line}: {e}")
            return None

    def _m3_spindle_speed_from_line(self, line):
        tokens = self._gcode_line_to_cmd_tokens(line)
        has_m3 = any(self._command_token_matches_base(token, "M3") for token in tokens)
        if not has_m3:
            return (False, None)

        for token in reversed(tokens):
            if token[:1].upper() != "S":
                continue
            try:
                return (True, float(token[1:]))
            except (ValueError, TypeError):
                continue
        return (True, None)

    def _find_last_feed_rate(self, lines=None, start_line=None, feed_lookup=None):
        """
        Return the feed rate (mm/min) in effect at start_line. Uses either pre-parsed
        feed data from the CNC parser or scans gcode lines.

        Args:
            lines: Gcode file lines (used when feed_lookup is None)
            start_line: Line number to search backwards from (1-based)
            feed_lookup: Optional dict mapping line_no (int) -> feed (float) from CNC
                         coordinates; when provided, lines is not scanned.

        Returns:
            Feed rate value as float, or None if not found
        """
        if feed_lookup is not None and start_line is not None:
            try:
                start_line = int(start_line)
            except (ValueError, TypeError):
                return None
            for line_no in range(start_line, 0, -1):
                if line_no in feed_lookup:
                    return feed_lookup[line_no]
            return None

        if not lines:
            return None

        try:
            # Ensure start_line is an integer
            try:
                start_line = int(start_line)
            except (ValueError, TypeError):
                logger.warning(f"Invalid start_line value: {start_line}")
                return None

            if start_line < 1 or start_line > len(lines):
                return None

            # F is modal independently of a motion command, so the most recent
            # feed word may be on a standalone or tightly packed G-code line.
            for i in range(start_line - 2, -1, -1):
                for token in reversed(self._gcode_line_to_cmd_tokens(lines[i])):
                    if token[:1].upper() != "F":
                        continue
                    try:
                        return float(token[1:])
                    except (ValueError, TypeError):
                        continue

            return None

        except Exception as e:
            logger.warning(f"Error finding feed rate before line {start_line}: {e}")
            return None

    def _gcode_line_to_cmd_tokens(self, original_line):
        """
        Split a physical line into G-code words the same way CNC.parseLine does.
        Handles multi-command blocks (e.g. 'G90 G94', 'G17 G21 G54') without false
        substring matches (e.g. G17 matching a search for G1).
        """
        line = original_line.strip()
        if not line or line[0] in ("%", "#", ";"):
            return []
        line = PARENPAT.sub("", line)
        line = SEMIPAT.sub("", line)
        if not line.strip():
            return []
        line = line.replace(" ", "")
        if not line:
            return []
        tokenized = CMDPAT.sub(r" \1", line).lstrip()
        return tokenized.split()

    def _command_token_matches_base(self, token, base_command):
        """True if token is the same modal word as base_command (G0/G00, but not G17 for G1)."""
        if not token or not base_command:
            return False
        t, b = token.upper(), base_command.upper()
        if t == b:
            return True
        if len(b) < 2 or len(t) < 2 or t[0] != b[0] or b[0] not in ("G", "M"):
            return False
        if "." in b or "." in t:
            return False
        try:
            return int(float(t[1:])) == int(float(b[1:]))
        except ValueError:
            return False

    def _is_tool_select_token(self, token):
        tu = token.upper()
        if len(tu) < 2 or tu[0] != "T":
            return False
        return tu[1:].isdigit()

    def _compose_m6_command_from_tokens(self, tokens, m6_index):
        """Build e.g. 'T4 M6' or 'M6 T4' from the line's tokens (same line as M6)."""
        parts = []
        if m6_index > 0 and self._is_tool_select_token(tokens[m6_index - 1]):
            parts.append(tokens[m6_index - 1].upper())
        parts.append(tokens[m6_index].upper())
        if m6_index + 1 < len(tokens) and self._is_tool_select_token(tokens[m6_index + 1]):
            parts.append(tokens[m6_index + 1].upper())
        return " ".join(parts)

    def _find_command_line_number(self, lines, start_line, gcode_command):
        """
        Search backwards from start_line to find the last occurrence of a gcode command.

        Args:
            lines: Gcode file lines (1-based line numbers index into this list)
            start_line: Line number to search backwards from (1-based)
            gcode_command: Literal gcode command to search for (e.g., "G20", "G21", "M3", "M6")
                          Can include parameters (e.g., "M3 S1000", "M6 T1")

        Returns:
            Tuple of (command_string, line_number). For M6, includes adjacent T on the same line
            (e.g. 'T4 M6'). Otherwise the matched modal word (e.g. G90 from 'G90 G94').
        """
        if not lines:
            return (None, None)

        try:
            # Ensure start_line is an integer
            try:
                start_line = int(start_line)
            except (ValueError, TypeError):
                logger.warning(f"Invalid start_line value: {start_line}")
                return (None, None)

            if start_line < 1 or start_line > len(lines) + 1:
                return (None, None)

            command_upper = gcode_command.upper().strip()
            base_command = command_upper.split()[0]

            for i in range(start_line - 2, -1, -1):
                tokens = self._gcode_line_to_cmd_tokens(lines[i])
                for ti in range(len(tokens) - 1, -1, -1):
                    token = tokens[ti]
                    if self._command_token_matches_base(token, base_command):
                        if base_command.upper() == "M6":
                            return (self._compose_m6_command_from_tokens(tokens, ti), i + 1)
                        return (token.upper(), i + 1)

        except Exception as e:
            logger.warning(f"Error finding command {gcode_command} before line {start_line}: {e}")

        return (None, None)

    def _has_movement_after_line(self, lines, after_line, before_start_line):
        """
        Return True if any G0–G3 command appears on a line strictly after after_line
        and before before_start_line.
        """
        for cmd in ("G0", "G1", "G2", "G3"):
            _, line_num = self._find_command_line_number(lines, before_start_line, cmd)
            if line_num is not None and line_num > after_line:
                return True
        return False

    def resume_playback_warnings(self, commands):
        """
        Inspect resume-at-line command preview and return missing-state warning keys.

        Returns a list that may include:
          - "tool_change": no M6 tool change in the recovery sequence
          - "feed": no G1 F feed rate restored
          - "spindle_speed": no M3 S spindle speed restored (skipped for laser/M321)
        """
        if not commands:
            return ["tool_change", "feed", "spindle_speed"]

        joined = "\n".join(commands).upper()
        warnings = []
        if not re.search(r"\bM0*6\b", joined):
            warnings.append("tool_change")
        if not re.search(r"\bG0*1\s+F\d", joined):
            warnings.append("feed")
        # Laser mode does not use spindle S recovery
        if not re.search(r"\bM321\b", joined) and not re.search(r"\bM0*3\s+S\d", joined):
            warnings.append("spindle_speed")
        return warnings

    def recovery_preview(self, filename, start_line, *, lines, clearance_machine_z_mm=None, has_ocodes=False):
        """Reconstruct a local review; opening this review never sends commands."""
        from .machine.recovery_plan import build_reentry, parse_words, reconstruct_recovery

        if has_ocodes:
            raise ValueError("Recovery of O-code programs requires a separately qualified interpreter")
        if not isinstance(filename, str) or not filename.strip() or any(c in filename for c in "\r\n\0\x01"):
            raise ValueError("Recovery requires a single exact machine filename")
        if type(start_line) is not int:
            raise ValueError("Recovery line must be an integer")
        if not isinstance(lines, (list, tuple)) or not 1 <= start_line <= len(lines):
            raise ValueError("Recovery line must identify a loaded physical line")
        for number, line in enumerate(lines[:start_line], 1):
            if not isinstance(line, str) or "\0" in line or len(line.encode("utf-8")) > 128:
                raise ValueError(f"Line {number} exceeds the firmware's safe 128-byte physical-line limit")
        # Parsed lines may have normalized CRLF. Verify the actual stored bytes
        # and hash so firmware fgets line numbers match the reviewed boundary.
        import stat

        program = self.run_evidence.program or {}
        try:
            fd = os.open(program.get("local_path", ""), os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
            with os.fdopen(fd, "rb") as source:
                if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                    raise ValueError("Recovery source must be a regular local file")
                if os.fstat(source.fileno()).st_size > MAX_EVIDENCE_LOG_BYTES:
                    raise ValueError("Recovery source exceeds the bounded 64 MiB validation limit")
                for number, parsed in enumerate(lines[:start_line], 1):
                    physical = source.readline(130)
                    if not physical or b"\0" in physical or len(physical) > 128:
                        raise ValueError(f"Stored line {number} exceeds the safe physical-line limit or is missing")
                    text = physical.decode("utf-8").replace("\r\n", "\n")
                    if "\r" in text or text.rstrip("\n") != parsed.rstrip("\r\n"):
                        raise ValueError(f"Stored physical line {number} differs from the reviewed program")
                source.seek(0)
                digest = hashlib.sha256()
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
                if digest.hexdigest() != program.get("sha256"):
                    raise ValueError("Local source bytes changed since the program was identified")
        except (OSError, UnicodeError) as error:
            raise ValueError("Recovery source cannot be verified: " + str(error)) from error
        self._program_request(filename, "recovery review")
        self._recovery_line = start_line
        state = reconstruct_recovery(lines, start_line)
        if any(("G", 20.0) in parse_words(line, number) for number, line in enumerate(lines[: start_line - 1], 1)):
            raise ValueError("Current firmware rejects G20 imperial execution; use a qualified millimeter program")
        context = self._recovery_context()
        if (context.get("modes") or [None] * 4)[3] != 1:
            raise ValueError("Prepare absolute G90 mode before recovery verification; firmware play selects G90")
        if self._recovery_disposal_nonce is not None:
            raise ValueError("Recovery buffer disposal awaits matching firmware acknowledgement and fresh Idle status")
        assessment = self.recovery_assessment(start_line)
        clearance = clearance_machine_z_mm
        if clearance is None:
            clearance = assessment["clearance_machine_z_mm"]
        work, machine = context.get("work_position"), context.get("machine_position")
        if not work or not machine:
            raise ValueError("Fresh work and machine XYZ are required to review an approach")
        approach = build_reentry(
            state,
            current_work_mm=work[:3],
            current_machine_z_mm=machine[2],
            clearance_machine_z_mm=clearance,
            verified_wcs_index=int(context["wcs"]),
            verified_tool=int(context["tool"]),
        )
        path = filename.replace("\\", "/").replace(" ", "\x01")
        commands = ["buffer M600", "play " + path, f"goto {start_line}"]
        commands.extend("buffer " + command for command in approach)
        commands.append("resume")
        return {
            "commands": commands,
            "summary": f"Before line {start_line}: {state.units} {state.distance}, tool {state.tool}, "
            f"work XYZ {state.position_mm}, feed {state.feed_mm_min} mm/min",
            "scope": assessment["scope"],
        }

    def _cancel_pending_recovery(self, reason):
        self._recovery_cancel_event.set()
        with self._adaptive_lock:
            active = self._recovery_pending_active
            self._recovery_pending_token += 1
            self._recovery_pending_active = False
            if self._recovery_scheduled is not None:
                self._recovery_scheduled.cancel()
                self._recovery_scheduled = None
            if active:
                self.log.put((self.MSG_ERROR, "Recovery approach cancelled: " + reason))
            if self._recovery_queue_dirty and self._recovery_disposal_nonce is None:
                self._recovery_nonce_counter = self._recovery_nonce_counter % 0xFFFFFFFF + 1
                self._recovery_disposal_nonce = self._recovery_nonce_counter
                self._request_recovery_buffer_disposal()

    def _request_recovery_buffer_disposal(self):
        """Transport receipt is insufficient: matching RB then fresh Idle clears this gate."""
        with self._adaptive_lock:
            if self._recovery_disposal_nonce is None:
                return False
            self._recovery_disposal_ack = False
            self._recovery_disposal_generation = self._connection_generation
            try:
                if not self.stream:
                    raise OSError("machine disconnected")
                payload = f"abort -R {self._recovery_disposal_nonce}\n".encode()
                self.stream.send(self.comms.encode_command(payload))
                self.log.put(
                    (
                        self.MSG_ERROR,
                        "Recovery cancelled; awaiting buffer disposal acknowledgement and fresh Idle status",
                    )
                )
                return True
            except Exception as error:
                self.log.put((self.MSG_ERROR, "Recovery buffer disposal unconfirmed: " + str(error)))
                return False

    def playStartLineCommand(self, filename, start_line, preview=False, lines=None, has_ocodes=False):
        if preview:
            return self.recovery_preview(filename, start_line, lines=lines, has_ocodes=has_ocodes)["commands"]
        with self._adaptive_lock:
            self._cancel_pending_recovery("new recovery request")
            try:
                with self._recovery_signal_lock:
                    if self._recovery_external_requests or self.stop.is_set():
                        raise ValueError("operator control or stop is pending")
                    self._recovery_cancel_event.clear()
                plan = self.recovery_preview(filename, start_line, lines=lines, has_ocodes=has_ocodes)
                assessment = self.recovery_assessment(start_line)
                if not assessment["allowed"]:
                    raise ValueError("; ".join(assessment["blockers"]))
                digest = hashlib.sha256()
                for line in lines:
                    digest.update(line.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8"))
                if digest.hexdigest() != (self.run_evidence.program or {}).get("parsed_lines_sha256"):
                    raise ValueError("passed G-code differs from identified loaded program")
                app = App.get_running_app() if App is not None else None
                if app is None or not app.is_community_firmware or app.fw_version_digitized < Utils.digitize_v("2.1.0"):
                    raise ValueError("qualified Community firmware goto semantics required (2.1.0 or later)")
                if not self._write_evidence(
                    {
                        "schema": "carvera.run.v1",
                        "kind": "recovery_plan",
                        "arrival_monotonic_s": self._evidence_now(),
                        "plan": plan,
                        "context": self.sensor_context_snapshot(),
                    }
                ):
                    raise ValueError("recovery plan could not be durably recorded")
                self._recovery_pending_active = True
                token = self._recovery_pending_token
                self._recovery_execution_deadline = self._evidence_now() + STATUS_REACQUIRE_TIMEOUT
                self._recovery_execution_generation = self._connection_generation
                self._recovery_queue_dirty = True
                for command in plan["commands"][:2]:
                    if not self.executeCommand(self.escape(command), recovery_token=token):
                        raise ValueError("initial pause/play command failed or cancelled")
                return self._wait_for_pause_and_continue_cmd_list_execution(plan["commands"][2:], token=token)
            except (TypeError, ValueError, KeyError) as error:
                self._cancel_pending_recovery(str(error))
                self.log.put((self.MSG_ERROR, "Recovery blocked: " + str(error)))
                return False

    def _wait_for_pause_and_continue_cmd_list_execution(self, remaining_commands, dt=None, *, token=None):
        """Bounded, generation-owned wait; stopped attempts cannot run later."""
        from .machine.recovery_policy import assess_recovery, recovery_scope

        with self._adaptive_lock:
            if token is None:
                token = self._recovery_pending_token
            if token != self._recovery_pending_token or not self._recovery_pending_active:
                return False
            if self._recovery_cancel_event.is_set() or self.stop.is_set():
                self._cancel_pending_recovery("operator stop or control")
                return False
            self._recovery_scheduled = None
            context = self._recovery_context()
            program = self.run_evidence.program or {}
            scope = recovery_scope(program.get("sha256"), self._recovery_line, context)
            if (
                self._connection_generation != self._recovery_execution_generation
                or self._evidence_now() >= self._recovery_execution_deadline
                or not self._recovery_verification
                or scope != self._recovery_verification.scope
            ):
                self._cancel_pending_recovery("pause timeout or verified state changed")
                return False
            if context.get("state") == "Pause":
                # Pause is the sole expected state transition. Every other live
                # constraint must still satisfy the same idle verification.
                check_context = dict(context, state="Idle")
                if not assess_recovery(
                    program.get("sha256"), self._recovery_line, check_context, self._recovery_verification
                )["allowed"]:
                    self._cancel_pending_recovery("fresh pause state does not satisfy verification")
                    return False
                for command in remaining_commands:
                    if not self.executeCommand(self.escape(command), recovery_token=token):
                        self._cancel_pending_recovery("recovery command failed or cancelled")
                        return False
                if self._recovery_cancel_event.is_set() or self.stop.is_set():
                    self._cancel_pending_recovery("operator control during final recovery write")
                    return False
                self._recovery_pending_active = False
                self._recovery_queue_dirty = False
                return True
            if context.get("state") not in ("Idle", "Run"):
                self._cancel_pending_recovery("unexpected machine state")
                return False
            if Clock is None:
                self._cancel_pending_recovery("scheduler unavailable")
                return False
            self._recovery_scheduled = Clock.schedule_once(
                partial(self._wait_for_pause_and_continue_cmd_list_execution, remaining_commands, token=token), 0.1
            )
            return True

    def abortCommand(self):
        if self._recovery_disposal_nonce is not None:
            self._signal_external_control()
            try:
                return self._request_recovery_buffer_disposal()
            finally:
                self._finish_external_control()
        return self.executeCommand("abort\n")

    def feedholdCommand(self):
        self.executeRealtime(ord("!"))

    def toggleFeedholdCommand(self, holding):
        if holding:
            self.executeRealtime(ord("~"))
        else:
            self.executeRealtime(ord("!"))

    def cyclestartCommand(self):
        self.executeRealtime(ord("~"))

    def estopCommand(self):
        self._instances.add(self)
        self.executeRealtime(0x18)

    # ----------------------------------------------------------------------
    def hardResetPre(self):
        self.executeCommand("reset\n")

    def hardResetAfter(self):
        time.sleep(6)

    def parseBracketAngle(self, line):
        with self._adaptive_lock, self._evidence_global_lock:
            return self._parse_status_packet(line)

    def _parse_status_packet(self, line):
        # R: Rotation Angle; G: active Coord System;
        # <Idle|MPos:68.9980,-49.9240,40.0000,12.3456|WPos:68.9980,-49.9240,40.0000,5.3|R:0.0|G:0|F:12345.12,100.0|S:1.2,100.0|T:1|L:0>
        # F: Feed, overide | S: Spindle RPM
        # Comms delivers newline-trimmed text; keep delimiter extraction so a
        # trailing junk byte after '>' cannot poison the last field.
        try:
            state, d = parse_numeric_fields(line, status=True)
        except ValueError:
            self.run_evidence.rejected += 1
            raise
        now = self._evidence_now()
        source = d.get("SE")
        if source:
            metadata = dict(
                zip(
                    (
                        "version",
                        "boot_id",
                        "boot_id_valid",
                        "sequence",
                        "tick_us",
                        "tick_wraps",
                        "valid_mask",
                        "position_source",
                        "feed_source",
                    ),
                    map(int, source[:9]),
                )
            )
            source_state = self.adaptive_monitor.quality.record_source(metadata)
            if source_state == "duplicate or reordered source sample":
                self.run_evidence.rejected += 1
                raise ValueError(source_state)
            if source_state in ("confirmed boot change", "source clock regression or reset"):
                self.adaptive_monitor.baseline = None
                self.adaptive_monitor.baseline_samples = []
                self.adaptive_monitor.fault = source_state + "; capture a fresh baseline"
        if not source:
            self.adaptive_monitor.quality.source_current_packet = False
            self.adaptive_monitor.quality.source_state = "unavailable in current packet"
        l = [state]
        CNC.vars["state"] = state
        record = self.run_evidence.observe(line, state, d, now)
        context = self.sensor_context_snapshot()
        record["context"] = context
        self.run_evidence.latest = context
        CNC.vars["sensor_context"] = context
        for key in ("spindle_temperature", "power_temperature", "probe_voltage"):
            CNC.vars[key + "_available"] = context[key] is not None
        CNC.vars["position_semantics"] = context["position_semantics"]
        CNC.vars["feed_semantics"] = context["feed_semantics"]
        fault = context.get("fault")
        if fault and int(fault[0]) != self._last_fault_dump_requested and int(fault[0]) > 0:
            self._fault_dump_pending = True
        if "R" in d:
            CNC.vars["rotation_angle"] = float(d["R"][0])
            CNC.can_rotate_wcs = True
        else:
            CNC.vars["rotation_angle"] = 0.0
        if "G" in d:
            CNC.vars["active_coord_system"] = int(d["G"][0])
        if "C" in d:
            CNC.vars["MachineModel"] = int(d["C"][0])
            CNC.vars["FuncSetting"] = int(d["C"][1])
            CNC.vars["inch_mode"] = int(d["C"][2])
            CNC.vars["absolute_mode"] = int(d["C"][3])
        if CNC.vars["inch_mode"] != 999:
            if CNC.vars["inch_mode"] == 1:
                CNC.UnitScale = 25.4
            else:
                CNC.UnitScale = 1
        else:
            CNC.UnitScale = 1
        CNC.vars["mx"] = float(d["MPos"][0])
        CNC.vars["my"] = float(d["MPos"][1])
        CNC.vars["mz"] = float(d["MPos"][2])
        if len(d["MPos"]) > 3:
            CNC.vars["ma"] = float(d["MPos"][3])
        else:
            CNC.vars["ma"] = 0.0
        CNC.vars["wx"] = float(d["WPos"][0])
        CNC.vars["wy"] = float(d["WPos"][1])
        CNC.vars["wz"] = float(d["WPos"][2])
        if len(d["WPos"]) > 3:
            CNC.vars["wa"] = float(d["WPos"][3])
        else:
            CNC.vars["wa"] = 0.0
        CNC.vars["wcox"] = round(
            CNC.vars["mx"]
            - (
                math.cos(CNC.vars["rotation_angle"] * math.pi / 180) * CNC.vars["wx"]
                - math.sin(CNC.vars["rotation_angle"] * math.pi / 180) * CNC.vars["wy"]
            ),
            3,
        )
        CNC.vars["wcoy"] = round(
            CNC.vars["my"]
            - (
                math.sin(CNC.vars["rotation_angle"] * math.pi / 180) * CNC.vars["wx"]
                + math.cos(CNC.vars["rotation_angle"] * math.pi / 180) * CNC.vars["wy"]
            ),
            3,
        )
        CNC.vars["wcoz"] = round(CNC.vars["mz"] - CNC.vars["wz"], 3)
        CNC.vars["wcoa"] = round(CNC.vars["ma"] - CNC.vars["wa"], 3)
        if "F" in d:
            CNC.vars["curfeed"] = float(d["F"][0])
            CNC.vars["tarfeed"] = float(d["F"][1])
            CNC.vars["OvFeed"] = int(d["F"][2])
            if len(d["F"]) > 3:  # Analog type spindle reports temp via F status for some reason in FW <= 2.1.0
                CNC.vars["spindletemp"] = float(d["F"][3])
        if "S" in d:
            CNC.vars["curspindle"] = float(d["S"][0])
            CNC.vars["tarspindle"] = float(d["S"][1])
            CNC.vars["OvSpindle"] = float(d["S"][2])
            s_fields = d["S"]
            if len(s_fields) > 3:
                CNC.vars["vacuummode"] = int(s_fields[3])
            if len(s_fields) >= 9 or len(s_fields) == 5:
                CNC.vars["spindletemp"] = float(s_fields[4])
            if len(s_fields) >= 8:
                CNC.vars["extoutmode"] = int(s_fields[-1])
        CNC.vars["has_spindle_pwm"] = "PWM" in d
        if "PWM" in d:
            CNC.vars["spindlepwm"] = float(d["PWM"][0])
            CNC.vars["has_spindle_pwm"] = True
        if "T" in d:
            CNC.vars["tool"] = int(d["T"][0])
            CNC.vars["tlo"] = float(d["T"][1])
            if len(d["T"]) > 2:
                CNC.vars["target_tool"] = int(d["T"][2])
            else:
                CNC.vars["target_tool"] = -1
            if len(d["T"]) > 3:
                CNC.vars["target_collet_type"] = int(d["T"][3])
            else:
                CNC.vars["target_collet_type"] = 0
        else:
            CNC.vars["tool"] = -1
            CNC.vars["tlo"] = 0.0
            CNC.vars["target_tool"] = -1
            CNC.vars["target_collet_type"] = 0
        if "W" in d:
            CNC.vars["wpvoltage"] = float(d["W"][0])
        if "L" in d:
            CNC.vars["lasermode"] = int(d["L"][0])
            CNC.vars["laserstate"] = int(d["L"][1])
            CNC.vars["lasertesting"] = int(d["L"][2])
            CNC.vars["laserpower"] = float(d["L"][3])
            CNC.vars["laserscale"] = float(d["L"][4])
        if "P" in d:
            CNC.vars["playedlines"] = int(d["P"][0])
            CNC.vars["playedpercent"] = int(d["P"][1])
            CNC.vars["playedseconds"] = int(d["P"][2])
            if len(d["P"]) >= 4:
                CNC.vars["is_playing"] = int(d["P"][3])
        else:
            # not playing file
            CNC.vars["playedlines"] = -1
            CNC.vars["is_playing"] = 0

        if "A" in d:
            CNC.vars["atc_state"] = int(d["A"][0])
        else:
            CNC.vars["atc_state"] = 0

        if "O" in d:
            CNC.vars["max_delta"] = float(d["O"][0])
        else:
            CNC.vars["max_delta"] = 0.0

        if "H" in d:
            CNC.vars["halt_reason"] = int(d["H"][0])

        from carveracontroller.machine.observed_pose import ObservedPose

        with self._adaptive_lock:
            self._last_status_received_at = now
            self._capability_observations["status_at"] = now
            self._receive_health.status(now)
            try:
                self.observed_pose = ObservedPose.from_packet(l[0], d, now)
                if (
                    self._recovery_disposal_nonce is not None
                    and self._recovery_disposal_ack
                    and self._recovery_disposal_generation == self._connection_generation
                    and l[0] == "Idle"
                ):
                    self._recovery_disposal_nonce = None
                    self._recovery_disposal_ack = False
                    self._recovery_queue_dirty = False
                    self._recovery_verification = None
                    self.log.put((self.MSG_NORMAL, "Recovery buffer disposal confirmed; fresh verification required"))
                if "C" in d:
                    self._capability_observations["has_atc"] = bool(int(d["C"][1]) & 4)
                if (
                    self._status_reacquire_started_at is not None
                    and self.observed_pose.timestamp >= self._status_reacquire_started_at
                ):
                    elapsed = self.observed_pose.timestamp - self._status_reacquire_started_at
                    self.log.put((self.MSG_NORMAL, f"Status reacquired after polling pause in {elapsed:.3f}s"))
                    self._status_reacquire_started_at = None
                    self._status_reacquire_deadline = None
            except (ValueError, TypeError, IndexError):
                self.observed_pose = None
        self._observe_adaptive(d, context=context, raw_frame=line, arrival=now)
        try:
            self.run_recording.capture_status(l[0], d, now, time.time(), self._connection_generation)
        except (ValueError, TypeError):
            logger.warning("Status packet could not be retained in the local run record")
        self.posUpdate = True

    def parseBigParentheses(self, line):
        with self._adaptive_lock, self._evidence_global_lock:
            return self._parse_diagnostic_packet(line)

    def _parse_diagnostic_packet(self, line):
        # {S:0,5000|L:0,0|F:1,0|V:0,1|G:0|T:0|E:0,0,0,0,0,0|P:0,0|A:1,0|RSSI:-57}
        # Comms delivers newline-trimmed text; keep delimiter extraction so a
        # trailing junk byte after '}' cannot poison the last field.
        try:
            _, d = parse_numeric_fields(line)
        except ValueError:
            self.run_evidence.rejected += 1
            raise
        now = self._evidence_now()
        record = self.run_evidence.observe_diagnostic(line, d, now)
        self._write_evidence(record, background=True)
        if "S" in d:
            CNC.vars["sw_spindle"] = int(d["S"][0])
            CNC.vars["sl_spindle"] = int(d["S"][1])
        if "L" in d:
            CNC.vars["sw_laser"] = int(d["L"][0])
            CNC.vars["sl_laser"] = int(d["L"][1])
        if "F" in d:
            CNC.vars["sw_spindlefan"] = int(d["F"][0])
            CNC.vars["sl_spindlefan"] = int(d["F"][1])
        if "V" in d:
            CNC.vars["sw_vacuum"] = int(d["V"][0])
            CNC.vars["sl_vacuum"] = int(d["V"][1])
        if "G" in d:
            CNC.vars["sw_light"] = int(d["G"][0])
        if "T" in d:
            CNC.vars["sw_tool_sensor_pwr"] = int(d["T"][0])
        if "R" in d:
            CNC.vars["sw_air"] = int(d["R"][0])
        if "C" in d:
            CNC.vars["sw_wp_charge_pwr"] = int(d["C"][0])

        if "E" in d:
            CNC.vars["st_x_min"] = int(d["E"][0])
            CNC.vars["st_x_max"] = int(d["E"][1])
            CNC.vars["st_y_min"] = int(d["E"][2])
            CNC.vars["st_y_max"] = int(d["E"][3])
            CNC.vars["st_z_max"] = int(d["E"][4])
            CNC.vars["st_cover"] = int(d["E"][5])
        if "P" in d:
            CNC.vars["st_probe"] = int(d["P"][0])
            CNC.vars["st_calibrate"] = int(d["P"][1])
        if "A" in d:
            CNC.vars["st_atc_home"] = int(d["A"][0])
            CNC.vars["st_tool_sensor"] = int(d["A"][1])
        if "I" in d:
            CNC.vars["st_e_stop"] = int(d["I"][0])
        if "RSSI" in d:
            CNC.vars["RSSI"] = int(d["RSSI"][0])

        self.diagnoseUpdate = True

    # ----------------------------------------------------------------------
    def help(self, event=None):
        webbrowser.open(WIKI, new=2)

    # ----------------------------------------------------------------------
    # Open serial port or wifi connect
    # ----------------------------------------------------------------------
    def _close_existing_connection(self):
        """Stop streamIO and close any active transport before opening a new one."""
        if self.stream is None and self.thread is None:
            return
        self.stopRun()
        thread = self.thread
        self.thread = None
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1.0)
        if self.stream is not None:
            try:
                self.stream.close()
            except Exception:
                pass
            self.stream = None
        self.comms.reset()
        self.clearRun()

    def open(self, conn_type, address):
        self._signal_external_control()
        self.stop.set()
        try:
            with self._adaptive_lock, self._evidence_global_lock:
                return self._open_connection(conn_type, address)
        finally:
            self._finish_external_control()

    def _open_connection(self, conn_type, address):
        # Baselines must never survive a connection handoff or reconnect.
        with self._adaptive_lock:
            self._connection_generation += 1
            generation = self._connection_generation
            self._capability_observations = {"generation": generation}
            self.slot_inventory.reset()
            self._connection_started_at = None
            self._last_status_received_at = None
            self._receive_health = ReceiveHealth(generation, time.monotonic())
            self._status_reacquire_started_at = None
            self._status_reacquire_deadline = None
            self._status_poll_requested = False
            self.adaptive_monitor.reset()
            selected_program = self.run_evidence.program
            self.run_evidence = RunEvidence()
            self.run_evidence.program = selected_program
            if selected_program:
                selected_program["machine_file_identity"] = "unverified"
                selected_program["request"] = "connection changed; machine file requires verification"
            self._last_fault_dump_requested = None
            self._fault_dump_pending = False
            self.observed_pose = None
        # init connection
        method = "USB serial" if conn_type == CONN_USB else "WiFi"
        # Single user-visible connect log (monitorSerial emits one MDI Received line).
        self.log.put((self.MSG_NORMAL, f"Connecting via {method}: {address}"))

        self.connection_type = conn_type
        # Persist the last connection target so callers can detect "same machine"
        # reconnects (e.g. for resume-at-line selection / loaded lines behavior).
        self.connection_address = address
        self._connecting = True
        self._heartbeat_grace_until = 0.0
        # Keep self.stream unset until open + protocol detect finish so heartbeat
        # cannot treat a half-open link as a live connection and tear it down.
        if conn_type == CONN_USB:
            transport = self.usb_stream
            self._baud_upgrade_attempted = False
        else:
            transport = self.wifi_stream

        try:
            # Switching WiFi ↔ USB (or reconnecting) must tear down the old link first.
            self._close_existing_connection()

            if not transport.open(address):
                self.log.put((self.MSG_ERROR, "Connection Failed!"))
                return False

            if conn_type == CONN_USB:
                # USB open toggles DTR and resets the machine; wait for firmware boot
                # before protocol probe / status polling.
                time.sleep(2.0)

            CNC.vars["state"] = CONNECTED
            CNC.vars["color"] = STATECOLOR[CNC.vars["state"]]
            self.log.put((self.MSG_NORMAL, "Connected to machine!"))
            self._gcount = 0
            self._alarm = True
            CNC.vars["alarm_message"] = ""
            # Reset manual disconnect flag when connection is established
            self._manual_disconnect = False
            try:
                self.clearRun()
            except Exception:
                self.log.put((self.MSG_ERROR, "Controller clear thread error!"))
            self.comms.detect_and_select(transport)
            self.stream = transport
            self._connection_started_at = time.monotonic()
            self.thread = threading.Thread(target=self.streamIO, args=(generation,))
            self._receive_threads.add(self.thread)
            self.thread.start()
            self._refresh_heartbeat = True
            # USB needs a longer post-reset grace; WiFi is usually ready immediately.
            self._heartbeat_grace_until = time.time() + (20.0 if conn_type == CONN_USB else 5.0)
            return True
        finally:
            self._connecting = False

    # ----------------------------------------------------------------------
    # Close connection port
    # ----------------------------------------------------------------------
    def close(self):
        self._signal_external_control()
        self.stop.set()
        try:
            return self._close_after_signal()
        finally:
            self._finish_external_control()

    def _close_after_signal(self):
        with self._adaptive_lock:
            self._connection_generation += 1
            self._recovery_verification = None
            self._cancel_pending_recovery("disconnect")
        if self.stream is None:
            return
        try:
            self.stopRun()
        except Exception:
            self.log.put((self.MSG_ERROR, "Controller stop thread error!"))
        self._runLines = 0
        thread = self.thread
        try:
            self.stream.close()
        except Exception:
            self.log.put((self.MSG_ERROR, "Controller close stream error!"))
        self.stream = None
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=0.5)
        self.thread = thread if thread is not None and thread.is_alive() else None
        self.comms.reset()
        CNC.vars["state"] = NOT_CONNECTED
        CNC.vars["color"] = STATECOLOR[CNC.vars["state"]]

        # Start reconnection if enabled (WiFi or USB; callback resolves the method).
        if self.reconnect_enabled and self.reconnect_callback:
            self.start_reconnection()

    def close_manual(self):
        self._signal_external_control()
        self.stop.set()
        try:
            return self._close_manual_after_signal()
        finally:
            self._finish_external_control()

    def _close_manual_after_signal(self):
        """Close connection manually (user initiated) - don't auto-reconnect"""
        with self._adaptive_lock:
            self._connection_generation += 1
            self._recovery_verification = None
            self._cancel_pending_recovery("disconnect")
        if self.stream is None:
            return
        method = "USB serial" if self.connection_type == CONN_USB else "WiFi"
        address = self.connection_address or "unknown"
        self.log.put((self.MSG_NORMAL, f"Disconnected via {method}: {address}"))
        try:
            self.stopRun()
        except Exception:
            self.log.put((self.MSG_ERROR, "Controller stop thread error!"))
        self._runLines = 0
        thread = self.thread
        try:
            self.stream.close()
        except Exception:
            self.log.put((self.MSG_ERROR, "Controller close stream error!"))
        self.stream = None
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=0.5)
        self.thread = thread if thread is not None and thread.is_alive() else None
        self.comms.reset()
        # Set a flag to indicate this was a manual disconnection
        self._manual_disconnect = True
        CNC.vars["state"] = NOT_CONNECTED
        CNC.vars["color"] = STATECOLOR[CNC.vars["state"]]

    def set_reconnection_config(self, enabled, wait_time, attempts):
        """Set reconnection configuration"""
        self.reconnect_enabled = enabled
        self.reconnect_wait_time = wait_time
        self.reconnect_attempts = attempts

    def set_reconnection_callbacks(self, reconnect_callback, cancel_callback, success_callback=None):
        """Set reconnection callbacks"""
        self.reconnect_callback = reconnect_callback
        self.cancel_reconnect_callback = cancel_callback
        self.reconnect_success_callback = success_callback

    def start_reconnection(self):
        """Start the reconnection process"""
        if not self.reconnect_enabled or not self.reconnect_callback:
            return

        self.reconnect_countdown = self.reconnect_wait_time
        self.reconnect_attempts_remaining = self.reconnect_attempts

        # Schedule the first reconnection attempt
        if self.reconnect_timer:
            self.reconnect_timer.cancel()
        self.reconnect_timer = threading.Timer(self.reconnect_wait_time, self.attempt_reconnect)
        self.reconnect_timer.start()

    def attempt_reconnect(self):
        """Attempt to reconnect"""
        self.reconnect_attempts_remaining -= 1

        # Try to reconnect using the callback
        if self.reconnect_callback:
            self.reconnect_callback()

        # Schedule next attempt if there are more attempts remaining
        if self.reconnect_attempts_remaining > 0:
            if self.reconnect_timer:
                self.reconnect_timer.cancel()
            self.reconnect_timer = threading.Timer(self.reconnect_wait_time, self.attempt_reconnect)
            self.reconnect_timer.start()
        else:
            # All attempts exhausted, call the cancel callback
            if self.cancel_reconnect_callback:
                self.cancel_reconnect_callback()

    def cancel_reconnection(self):
        """Cancel the reconnection process"""
        if self.reconnect_timer:
            self.reconnect_timer.cancel()
            self.reconnect_timer = None
        # Reset reconnection state
        self.reconnect_countdown = 0
        self.reconnect_attempts_remaining = 0
        if self.cancel_reconnect_callback:
            self.cancel_reconnect_callback()

    def notify_reconnection_success(self):
        """Notify that reconnection was successful"""
        if self.reconnect_success_callback:
            self.reconnect_success_callback()

    # ----------------------------------------------------------------------
    def stopRun(self):
        self.stop.set()
        self._cancel_pending_recovery("stop or disconnect")

    # ----------------------------------------------------------------------
    def clearRun(self):
        self.stop.clear()

    # ----------------------------------------------------------------------
    # Send to controller a gcode or command
    # WARNING: it has to be a single line!
    # ----------------------------------------------------------------------
    def sendGCode(self, cmd):
        self.executeCommand(cmd)

    # ----------------------------------------------------------------------
    def sendHex(self, hexcode):
        if self.stream is None:
            return
        self.executeRealtime(int(hexcode, 16))

    def viewStatusReport(self, sio_status):
        if self.loadNUM == 0 and self.sendNUM == 0:
            if self.stream is None or not self.protocol_ready:
                return
            if (
                self.continuous_jog_active
                and not self._continuous_jog_stopping
                and not self.status_reacquisition_pending
            ):
                # Smoothie uses "?1"; Makera uses "?" + Ctrl+Z keepalive.
                # Always one write so keepalive can't be interleaved/orphaned.
                if self.comms.uses_framed_transfer:
                    self.executeRealtimeSequence(ord("?"), 0x1A)
                else:
                    self.executeRealtimeSequence(ord("?"), ord("1"))
            else:
                self.executeRealtime(ord("?"))
            self.sio_status = sio_status

    def viewDiagnoseReport(self, sio_diagnose):
        if self.loadNUM == 0 and self.sendNUM == 0:
            if self.stream is None or not self.protocol_ready:
                return
            self.executeCommand("diagnose\n")
            self.sio_diagnose = sio_diagnose
            self._diagnose_requested_at = self._evidence_now()

    # ----------------------------------------------------------------------
    def hardReset(self):
        self.busy()
        if self.stream is not None:
            self.hardResetPre()
            self.openClose()
            self.hardResetAfter()
        self.openClose()
        self.stopProbe()
        self._alarm = False
        CNC.vars["alarm_message"] = ""
        CNC.vars["_OvChanged"] = True  # force a feed change if any
        self.notBusy()

    def softReset(self, clearAlarm=True):
        self.executeRealtime(0x18)
        self.stopProbe()
        if clearAlarm:
            self._alarm = False
            CNC.vars["alarm_message"] = ""
        CNC.vars["_OvChanged"] = True  # force a feed change if any

    def unlock(self, clearAlarm=True):
        if clearAlarm:
            self._alarm = False
            CNC.vars["alarm_message"] = ""
        self.sendGCode("$X")

    def home(self, event=None):
        self.sendGCode("$H")

    def viewSettings(self):
        pass

    def viewParameters(self):
        self.sendGCode("$#")

    def viewWCS(self):
        self.sendGCode("get wcs")

    def viewState(self):
        self.sendGCode("$G")

    def viewBuild(self):
        self.executeCommand("version\n")
        self.sendGCode("$I")

    def viewStartup(self):
        pass

    def checkGcode(self):
        pass

    def grblHelp(self):
        self.executeCommand("help\n")

    def grblRestoreSettings(self):
        pass

    def grblRestoreWCS(self):
        pass

    def grblRestoreAll(self):
        pass

    # ----------------------------------------------------------------------
    def setJogMode(self, mode):
        """Set the jog mode (step or continuous)"""
        if not self.is_community_firmware:
            return

        if mode in [Controller.JOG_MODE_STEP, Controller.JOG_MODE_CONTINUOUS]:
            if self.continuous_jog_active:
                self.stopContinuousJog()
            self.jog_mode = mode

    def startContinuousJog(self, _dir, speed=None, scale_feed_override=None):
        """Start continuous jogging in the specified direction"""
        if (
            self.status_reacquisition_pending
            or self.jog_mode != Controller.JOG_MODE_CONTINUOUS
            or self.continuous_jog_active
            or self._continuous_jog_stopping
        ):
            return
        self.continuous_jog_active = True
        self._continuous_jog_stopping = False
        if speed is None:
            if self.jog_speed > 0 and self.jog_speed < 10000:
                self.executeCommand(f"$J -c {_dir} F{self.jog_speed}")
            else:
                if scale_feed_override is not None:
                    self.executeCommand(f"$J -c {_dir} {scale_feed_override}")
                else:
                    self.executeCommand(f"$J -c {_dir}")
        else:
            self.executeCommand(f"$J -c {_dir} F{speed}")

    def stopContinuousJog(self):
        """Stop continuous jogging"""

        if self.jog_mode != Controller.JOG_MODE_CONTINUOUS:
            return

        # Send Ctrl+Y, then wait for firmware ^Y before allowing a new $J -c.
        # Mark stopping immediately so status polls stop sending keepalives that
        # would otherwise fight the stop request.
        if self.stream is not None and self.continuous_jog_active and not self._continuous_jog_stopping:
            self._continuous_jog_stopping = True
            self.executeRealtime(0x19)

    def _clear_continuous_jog_state(self):
        self.continuous_jog_active = False
        self._continuous_jog_stopping = False

    def jog(self, _dir, speed=None):
        if self.jog_mode == Controller.JOG_MODE_STEP:
            if speed is None:
                if self.jog_speed == 0:
                    self.executeCommand(f"$J {_dir}")
                else:
                    self.executeCommand(f"$J {_dir} F{self.jog_speed}")
            else:
                self.executeCommand(f"$J {_dir} F{speed}")
        elif self.jog_mode == Controller.JOG_MODE_CONTINUOUS:
            self.startContinuousJog(_dir)

    # ----------------------------------------------------------------------

    def goto(self, x=None, y=None, z=None):
        cmd = "G90G0"
        if x is not None:
            cmd += "X%g" % (x)
        if y is not None:
            cmd += "Y%g" % (y)
        if z is not None:
            cmd += "Z%g" % (z)
        self.sendGCode("%s" % (cmd))

    def gotoSafeZ(self):
        # using 2mm below the homing point as CA1 x-sag compensation could be a whole mm
        self.sendGCode("G53 G0 Z-2")

    def gotoMachineHome(self):
        self.gotoSafeZ()
        # CA1 x-sag compensation could be a whole mm in Y, so use 2mm to be safe. Same for X for consistency
        self.sendGCode("G53 G0 X-2 Y-2")

    def gotoWCSHome(self):
        self.gotoSafeZ()
        self.sendGCode("G53 G0 X%g Y%g" % (CNC.vars["wcox"], CNC.vars["wcoy"]))

    def wcs_set_a(self, a=None):
        cmd = "G10L20P0"
        if a is not None and abs(a) < 3600000.0:
            cmd += "A" + str(round(a, 5))

        self.sendGCode(cmd)

    def shrinkA(self):
        self.sendGCode("G92.4 A0 S0")

    def rapid_move_a(self, a=None):
        cmd = "G90G0"
        cmd += "X" + str(round(a, 5))
        cmd = "G92.4"
        cmd += " A " + str(round(a, 5)) + " R0"
        if a is not None and abs(a) < 3600000.0:
            self.sendGCode(cmd)

    def wcs_set(self, x=None, y=None, z=None, a=None):
        cmd = "G10L20P0"

        pos = ""
        if x is not None and abs(x) < 10000.0:
            pos += "X" + str(round(x, 4))
        if y is not None and abs(y) < 10000.0:
            pos += "Y" + str(round(y, 4))
        if z is not None and abs(z) < 10000.0:
            pos += "Z" + str(round(z, 4))
        if a is not None and abs(a) < 3600000.0:
            pos += "A" + str(round(a, 4))
        cmd += pos

        self.sendGCode(cmd)

    def wcsSetM(self, x=None, y=None, z=None, a=None):
        # p = WCS.index(CNC.vars["WCS"])
        cmd = "G10L2P0"

        pos = ""
        if x is not None and abs(x) < 10000.0:
            pos += "X" + str(round(x, 4))
        if y is not None and abs(y) < 10000.0:
            pos += "Y" + str(round(y, 4))
        if z is not None and abs(z) < 10000.0:
            pos += "Z" + str(round(z, 4))
        if a is not None and abs(a) < 3600000.0:
            pos += "A" + str(round(a, 4))
        cmd += pos

        self.sendGCode(cmd)

    def wcsClearRotation(self):
        cmd = "G10L2R0P0"
        self.sendGCode(cmd)

    def setRotation(self, rotation):
        """Set the rotation angle for the current coordinate system"""
        cmd = f"G10L2R{rotation:.3f}P0"
        self.sendGCode(cmd)

    def feedHold(self, event=None):
        if event is not None and not self.acceptKey(True):
            return
        if self.stream is None:
            return
        self.executeRealtime(ord("!"))
        self._pause = True

    def resume(self, event=None):
        if event is not None and not self.acceptKey(True):
            return
        if self.stream is None:
            return
        self.executeRealtime(ord("~"))
        self._alarm = False
        CNC.vars["alarm_message"] = ""
        self._pause = False

    def pause(self, event=None):
        if self.stream is None:
            return
        if self._pause:
            self.resume()
        else:
            self.feedHold()

    # ----------------------------------------------------------------------
    def _drain_stream_messages(self, timeout_s=0.3):
        """Read and parse pending RX bytes for up to timeout_s; return messages."""
        messages = []
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if not self.stream or not self.stream.waiting_for_recv():
                time.sleep(0.01)
                continue
            data = self.stream.recv()
            if data:
                messages.extend(self.comms.feed(data, allow_wire_switch=False))
        return messages

    def _flush_rx(self):
        """Discard any unread host RX bytes and reset the protocol parser."""
        serial_port = getattr(self.stream, "serial", None) if self.stream else None
        if serial_port is not None:
            try:
                serial_port.reset_input_buffer()
            except Exception:
                pass
            try:
                while serial_port.in_waiting:
                    serial_port.read(serial_port.in_waiting)
            except Exception:
                pass
        self.comms.reset_parser()

    @staticmethod
    def _looks_like_status(text):
        t = (text or "").lstrip()
        return t.startswith("<") and ("|" in t or "MPos" in t or "Idle" in t or "Run" in t)

    def _await_status_response(self, timeout_s=1.0):
        """Send a status query and wait for a status frame/line."""
        self.executeRealtime(ord("?"))
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            for message in self._drain_stream_messages(timeout_s=0.05):
                if self._looks_like_status(message.text):
                    return True
        return False

    def request_baud_upgrade(self, baud):
        """Send firmware baud command, then switch the host UART to match."""
        if self.connection_type != CONN_USB or self.stream != self.usb_stream:
            return
        if not hasattr(self.usb_stream, "reopen_at_baud"):
            return
        if self.sendNUM != 0 or self.loadNUM != 0:
            self.log.put((self.MSG_ERROR, "Failed to change serial speed: transfer in progress"))
            return
        baud = int(baud)
        self._baud_switch_in_progress = True
        self._refresh_heartbeat = True
        # Stop streamIO and wait until it is parked so it cannot steal the "ok".
        try:
            self.pauseStream(0.0)
            self.executeCommand(f"baud {baud}\n")
            # Firmware prints framed/text "ok" at the old baud, then switches.
            # Give TX time to finish, then reopen the host port at the new rate.
            time.sleep(0.15)
            self._flush_rx()
            if not self.usb_stream.reopen_at_baud(baud):
                raise RuntimeError("Failed to set host serial baud rate")
            # Ensure Controller still points at the reopened USB stream.
            self.stream = self.usb_stream
            self.comms.reset_parser()
            if not self._await_status_response(timeout_s=1.5):
                # Recover: try bringing both sides back to 115200.
                self._recover_baud_after_failed_upgrade(baud)
                raise RuntimeError(f"no status response after switching to {baud} baud")
            self.log.put((self.MSG_NORMAL, f"Serial speed set to {baud} baud"))
            self._refresh_heartbeat = True
        except Exception as e:
            self.log.put((self.MSG_ERROR, f"Failed to change serial speed: {e}"))
            self._refresh_heartbeat = True
        finally:
            self._baud_switch_in_progress = False
            self.resumeStream()

    def _recover_baud_after_failed_upgrade(self, attempted_baud):
        """Best-effort restore of 115200 after a failed high-baud switch."""
        try:
            # Machine may already be at attempted_baud — ask it to drop back.
            self.executeCommand("baud 115200\n")
            time.sleep(0.15)
        except Exception:
            pass
        try:
            self._flush_rx()
            if self.usb_stream.reopen_at_baud(115200):
                self.stream = self.usb_stream
            self.comms.reset_parser()
        except Exception:
            logger.exception("Failed to revert host baud to 115200 after upgrade to %s", attempted_baud)

    # ----------------------------------------------------------------------
    def parseLine(self, line):
        with self._adaptive_lock:
            return self._parse_line_unlocked(line)

    def _parse_line_unlocked(self, line):
        if not line:
            return True
        with self._adaptive_lock:
            self.slot_inventory.feed(line, self._connection_generation, time.monotonic())
        try:
            if line[0] == "<":
                self.parseBracketAngle(line)
                self.sio_status = False
            elif line.startswith("{RB:"):
                match = re.fullmatch(r"\{RB:1,([1-9][0-9]{0,9})\}", line)
                if (
                    match
                    and int(match.group(1)) == self._recovery_disposal_nonce
                    and self._connection_generation == self._recovery_disposal_generation
                ):
                    self._recovery_disposal_ack = True
                    self.log.put((self.MSG_NORMAL, "Firmware recovery buffer cleared; awaiting fresh Idle status"))
                else:
                    self.log.put((self.MSG_ERROR, "Unmatched recovery buffer acknowledgement ignored"))
            elif line.startswith("{PRH:"):
                _, fields = parse_numeric_fields(line)
                if len(fields.get("PRH", ())) != 15:
                    raise ValueError("invalid raw probe hit frame")
                self._write_evidence(
                    {
                        "schema": "carvera.run.v1",
                        "kind": "probe_hit",
                        "raw_frame": line,
                        "arrival_monotonic_s": self._evidence_now(),
                        "fields": fields,
                        "context": self.sensor_context_snapshot(),
                    },
                    background=True,
                )
                self.log.put((self.MSG_NORMAL, line))
            elif line.startswith(("{EV:", "{EH:", "{EE:")):
                self._write_evidence(self.run_evidence.observe_event(line, self._evidence_now()), background=True)
            elif line[0] == "{":
                if not self.sio_diagnose:
                    self.log.put((self.MSG_NORMAL, line))
                else:
                    self.parseBigParentheses(line)
                    self.sio_diagnose = False
            elif line[0] == "[" in line:
                # Log raw WCS parameters before parsing
                self.log.put((self.MSG_NORMAL, line))
                # Parse WCS parameters: [G54:-123.6800,-123.6800,-123.6800,-50,0.000,25.123]
                self.parseWCSParameters(line)
            elif line[0] == "#":
                self.log.put((self.MSG_INTERIOR, line))
            elif line[0] == "^":
                if line[1] == "Y":
                    self._clear_continuous_jog_state()
            elif "error" in line.lower() or "alarm" in line.lower():
                self._cancel_pending_recovery("machine alarm")
                self._write_evidence(
                    {
                        "schema": "carvera.run.v1",
                        "kind": "alarm",
                        "raw_frame": line,
                        "arrival_monotonic_s": self._evidence_now(),
                        "context": self.sensor_context_snapshot(),
                    },
                    background=True,
                )
                self.log.put((self.MSG_ERROR, line))
                if line.upper().startswith("ERROR:"):
                    msg = line[len("ERROR:") :].strip()
                    if msg:
                        CNC.vars["alarm_message"] = msg
            else:
                version = re.fullmatch(r"version\s*=\s*([0-9]+\.[0-9]+\.[0-9]+[a-zA-Z0-9\-_]*)", line.strip())
                model = re.fullmatch(r"model\s*=\s*(\w+),\s*(\d+),\s*(\d+),\s*(\d+)", line.strip())
                if version or model:
                    with self._adaptive_lock:
                        self._capability_observations["identity_at"] = time.monotonic()
                        if version:
                            self._capability_observations["firmware"] = version.group(1)
                        if model:
                            self._capability_observations["model"] = model.group(1)
                            self._capability_observations["has_atc"] = bool(int(model.group(3)) & 4)
                # Firmware continuous-jog timeout: clear local state so jogging can restart.
                if "Stop request timeout" in line or "Internal stop request reset" in line:
                    self._clear_continuous_jog_state()
                self.log.put((self.MSG_NORMAL, line))
        except (LookupError, ArithmeticError, ValueError) as e:
            self.log.put((self.MSG_ERROR, f"Failed to parse machine response: {line}"))
            logger.error(f"Parser error in parseLine: {e}, line: {line}")

    # ----------------------------------------------------------------------
    def g28Command(self):
        self.sendGCode("G28.1")  # FIXME: ???

    def g30Command(self):
        self.sendGCode("G30.1")  # FIXME: ???

    # ----------------------------------------------------------------------
    def emptyQueue(self):
        while self.queue.qsize() > 0:
            try:
                self.queue.get_nowait()
            except Empty:
                break

    def pauseStream(self, wait_s=0.0):
        """Stop the streamIO RX loop so file transfer owns the byte stream."""
        self.pausing = True
        # Pause RX immediately — do not wait before setting paused, or framed
        # file-transfer packets (MD5/etc.) can be consumed by streamIO.
        self.paused = True
        # Wait until streamIO acknowledges the pause before the caller touches RX.
        deadline = time.monotonic() + 1.0
        while not self._stream_io_parked and time.monotonic() < deadline:
            time.sleep(0.01)
        if not self._stream_io_parked:
            self.paused = False
            self.pausing = False
            raise TimeoutError("Receiver did not park; file transfer was not started")
        if wait_s > 0:
            time.sleep(wait_s)
        self.pausing = False

    def resumeStream(self):
        with self._adaptive_lock:
            if self.paused and self.stream is not None:
                # Transfer bytes are not pose evidence. Preserve the old status
                # timestamp and give the resumed receiver one bounded chance to
                # obtain a new packet before the UI watchdog disconnects it.
                now = time.monotonic()
                self._status_reacquire_started_at = now
                self._status_reacquire_deadline = now + STATUS_REACQUIRE_TIMEOUT
                self._status_poll_requested = True
                self.log.put((self.MSG_NORMAL, "Polling resumed; awaiting fresh status for up to 5.0s"))
            self.paused = False
            self.pausing = False
            self._stream_io_parked = False

    def status_reacquisition_remaining(self, now):
        """Bounded receive transition, never a substitute for fresh pose evidence."""
        with self._adaptive_lock:
            deadline = self._status_reacquire_deadline
            started = self._status_reacquire_started_at
            if (
                self.stream is None
                or self.paused
                or deadline is None
                or started is None
                or not math.isfinite(now)
                or now < started
            ):
                return 0.0
            return max(0.0, deadline - now)

    @property
    def status_reacquisition_pending(self):
        """Remain unready even after expiry until status arrives or link closes."""
        with self._adaptive_lock:
            return self.stream is not None and self._status_reacquire_started_at is not None

    def _handle_protocol_message(self, message):
        """Dispatch a ParsedMessage from the active communication protocol."""
        if message.kind == MessageKind.LOAD_EOF:
            self.loadEOF = True
            return
        if message.kind == MessageKind.LOAD_ERROR:
            self.loadERR = True
            return

        text = message.text or ""
        if message.kind == MessageKind.LOAD_CHUNK:
            cleaned = re.sub(r"<.*?>", "", text).strip()
            if not cleaned:
                return
            for line2 in cleaned.replace("\r\n", "\n").split("\n"):
                if line2:
                    self.load_buffer.put(line2)
                    self.load_buffer_size += len(line2) + 1
            return

        # LINE
        if self.loadNUM == 0 or "|MPos" in text:
            self.parseLine(text)
            return
        cleaned_line = re.sub(r"<.*?>", "", text).strip()
        if cleaned_line:
            for line2 in cleaned_line.replace("\r\n", "\n").split("\n"):
                if line2:
                    self.load_buffer.put(line2)
                    self.load_buffer_size += len(line2) + 1

    # ----------------------------------------------------------------------
    # thread performing I/O on serial line
    # ----------------------------------------------------------------------
    def adaptiveCommand(self, command):
        """Validate and save operator changes before activating advisory state."""
        from .machine.evidence_io import decode_json

        with self._adaptive_lock:
            parts = command.split(maxsplit=2)
            action = parts[1].lower() if len(parts) > 1 else "status"
            try:
                if action == "status":
                    self.log.put(
                        (self.MSG_NORMAL, "Adaptive " + json.dumps(self.adaptive_monitor.snapshot(), allow_nan=False))
                    )
                    return True
                candidate = deepcopy(self.adaptive_monitor)
                record = {
                    "schema": "carvera.run.v1",
                    "arrival_monotonic_s": self._evidence_now(),
                    "context": self.sensor_context_snapshot(),
                }
                if action in ("recipe", "outcome"):
                    if len(parts) != 3:
                        raise ValueError("recipe/outcome requires an object")
                    data = decode_json(parts[2])
                    if action == "recipe":
                        candidate.configure_recipe(data)
                    else:
                        candidate.record_outcome(data)
                    record.update(kind=action, data=data)
                elif action in ("baseline", "reset", "off", "shadow"):
                    if len(parts) != 2:
                        raise ValueError("unexpected advisory command arguments")
                    if action == "baseline":
                        candidate.capture_baseline()
                    elif action == "reset":
                        candidate.reset()
                    else:
                        candidate.enabled = action == "shadow"
                    record.update(kind="advisory_control", action=action)
                else:
                    raise ValueError(
                        "Local commands: adaptive status / baseline / reset / off / shadow / recipe / outcome"
                    )
                if not self._write_evidence(record):
                    return False
                self.adaptive_monitor = candidate
                self.log.put((self.MSG_NORMAL, "Adaptive " + json.dumps(candidate.snapshot(), allow_nan=False)))
                return True
            except (OSError, ValueError, TypeError) as error:
                self.log.put((self.MSG_ERROR, "Adaptive: " + str(error)))
                return False

    def _observe_adaptive(self, fields, *, context=None, raw_frame=None, arrival=None):
        # Use only the current packet. Missing fields cannot inherit old RPM/PWM.
        with self._adaptive_lock:
            now = self._evidence_now() if arrival is None else arrival
            missing = tuple(key for key in ("S", "F", "MPos") if len(fields.get(key, ())) < 3)
            if context and context.get("field_validity", {}).get("spindle_status") is False:
                missing += ("S_validity",)
            if missing:
                self.adaptive_monitor.quality.record(now, missing=missing)
                self.adaptive_monitor.proposal_eligible = False
                self.adaptive_monitor.proposal_blocker = "current packet lacks valid " + ", ".join(missing)
            else:
                sample = Sample(
                    now,
                    CNC.vars["state"],
                    fields["S"][0],
                    fields["S"][1] * fields["S"][2] / 100,
                    fields["PWM"][0] if fields.get("PWM") else None,
                    fields["F"][0],
                    fields["F"][2],
                    tuple(fields["MPos"][:3]),
                    context=context or {},
                )
                self.adaptive_monitor.quality.record(
                    now, valid=sample.valid(), rpm=sample.rpm, pwm_available=sample.pwm is not None
                )
                self.adaptive_monitor.observe(sample, packet_quality_recorded=True)
            decision = self.adaptive_monitor.snapshot(now)
            record = {
                "schema": "carvera.run.v1",
                "kind": "status",
                "raw_frame": raw_frame,
                "arrival_monotonic_s": now,
                "context": context,
                "utc": datetime.now(timezone.utc).isoformat(),
                "packet_complete": not missing,
                **decision,
            }
            self._write_evidence(record, background=True)

            if self._telemetry_logging_closed or not self._evidence_writes_enabled:
                return
            if self._adaptive_log is None:
                folder = Path(os.environ.get("KIVY_HOME", str(Path.home() / ".kivy"))) / "adaptive"
                self.adaptive_log_path = folder / (
                    datetime.now(timezone.utc).strftime("telemetry-%Y%m%dT%H%M%S")
                    + f"-{os.getpid()}-{uuid4().hex}.jsonl"
                )
                self._adaptive_log = TelemetryLog(
                    self.adaptive_log_path,
                    on_error=lambda error: self.log.put((self.MSG_ERROR, "Adaptive logging stopped: " + error)),
                )
            record = {
                "utc": datetime.now(timezone.utc).isoformat(),
                "connection_generation": self._connection_generation,
                "packet_complete": not missing,
                **decision,
            }
            self._adaptive_log.submit(record)

    def telemetry_persistence(self):
        """Storage observations only; cannot establish machine freshness."""
        with self._adaptive_lock:
            writer = self._adaptive_log
            return (
                {
                    **writer.snapshot(),
                    "recovery": self._telemetry_recovery.snapshot(),
                    "prior_lost_records": self._telemetry_prior_lost,
                }
                if writer
                else None
            )

    def resume_telemetry_logging(self):
        """Start one asynchronous local recovery; no transport or monitor reset."""
        with self._adaptive_lock:
            previous = self._adaptive_log
            if previous is None or self._telemetry_logging_closed:
                return False
            generation = self._connection_generation

            def publish(candidate, operation):
                with self._adaptive_lock:
                    if (
                        self._telemetry_logging_closed
                        or self._adaptive_log is not previous
                        or generation != self._connection_generation
                    ):
                        return None
                    final = previous.snapshot()
                    lost = self._telemetry_prior_lost + final["rejected"] + final["failed"]
                    boundary = {
                        "record_type": "telemetry_recovery_boundary",
                        "operation_id": operation,
                        "utc": datetime.now(timezone.utc).isoformat(),
                        "connection_generation": generation,
                        "previous": final,
                        "prior_lost_records": lost,
                        "complete_run": False,
                    }
                    if not candidate.submit(boundary):
                        return None
                    self._adaptive_log = candidate
                    self.adaptive_log_path = candidate.path
                    self._telemetry_prior_lost = lost
                    previous.close(0)
                    return boundary

            return self._telemetry_recovery.start(
                previous,
                previous.path.parent,
                publish,
                metadata={"connection_generation": generation, "prior_lost_records": self._telemetry_prior_lost},
                on_error=lambda error: self.log.put((self.MSG_ERROR, "Adaptive logging stopped: " + error)),
            )

    def stop_telemetry_logging(self, timeout=1.0):
        with self._adaptive_lock:
            self._telemetry_logging_closed = True
            writer = self._adaptive_log
        self._telemetry_recovery.close()
        receipt = writer.close(timeout) if writer else None
        if receipt is not None:
            self.log.put((self.MSG_NORMAL, "Telemetry persistence shutdown: " + json.dumps(receipt, allow_nan=False)))
        return receipt

    def _recovery_context(self):
        context = self.sensor_context_snapshot()
        source = context.get("source") or {}
        context["firmware_boot_id"] = source.get("boot_id") if source.get("boot_id_valid") else None
        context["connection_generation"] = self._connection_generation
        context["connection_address"] = str(self.connection_address or "")
        program = self.run_evidence.program or {}
        context["machine_filename"] = program.get("requested_machine_path")
        context["program"] = {
            "sha256": program.get("sha256"),
            "machine_filename": context["machine_filename"],
            "machine_file_identity": program.get("machine_file_identity"),
        }
        age = context.get("arrival_age_s")
        context["telemetry_stale"] = age is None or age > 0.8 or self.status_reacquisition_pending
        position, work = context.get("machine_position"), context.get("work_position")
        context["work_offset"] = None
        if position and work and context.get("rotation") is not None:
            angle = math.radians(context["rotation"])
            rotated = (
                math.cos(angle) * work[0] - math.sin(angle) * work[1],
                math.sin(angle) * work[0] + math.cos(angle) * work[1],
                work[2],
            )
            context["work_offset"] = [a - b for a, b in zip(position[:3], rotated)]
        return context

    def recovery_assessment(self, start_line):
        from .machine.recovery_policy import assess_recovery

        context = self._recovery_context()
        program = self.run_evidence.program or {}
        result = assess_recovery(program.get("sha256"), start_line, context, self._recovery_verification)
        if self._recovery_disposal_nonce is not None:
            result["blockers"].append(
                "recovery buffer disposal requires matching firmware acknowledgement and fresh Idle; Unlock if halted, then Abort to retry"
            )
        if self.stop.is_set():
            result["blockers"].append("controller stop is set")
        modes = context.get("modes")
        if isinstance(modes, (list, tuple)) and len(modes) == 4 and modes[3] != 1:
            result["blockers"].append("prepare absolute G90 mode before verification")
        result["allowed"] = not result["blockers"]
        return result

    def recoveryCommand(self, command):
        from dataclasses import asdict

        from .machine.recovery_policy import RecoveryVerification

        parts = command.split(maxsplit=2)
        action = parts[1].lower() if len(parts) > 1 else "status"
        with self._adaptive_lock:
            try:
                if action == "status":
                    line = int(parts[2]) if len(parts) == 3 else self._recovery_line
                    self._recovery_line = line
                elif action == "verify" and len(parts) == 3:
                    from .machine.evidence_io import decode_json

                    if self._recovery_disposal_nonce is not None or self.stop.is_set():
                        raise ValueError("Complete buffer disposal and clear the controller stop before verification")
                    data = decode_json(parts[2])
                    if not isinstance(data, dict):
                        raise ValueError("recovery verification requires an object")
                    line = data.pop("start_line", self._recovery_line)
                    verification = RecoveryVerification(**data)
                    assessment = self.recovery_assessment(line)
                    if assessment["scope"] != verification.scope:
                        raise ValueError("recovery scope changed; obtain current recovery status")
                    if not self._write_evidence(
                        {
                            "schema": "carvera.run.v1",
                            "kind": "recovery_verification",
                            "arrival_monotonic_s": self._evidence_now(),
                            "data": asdict(verification),
                            "start_line": line,
                            "context": self.sensor_context_snapshot(),
                        }
                    ):
                        return False
                    self._recovery_line = line
                    self._recovery_verification = verification
                else:
                    raise ValueError("Local commands: recovery status <line> / verify <JSON>")
                result = self.recovery_assessment(line)
                self._write_evidence(
                    {
                        "schema": "carvera.run.v1",
                        "kind": "recovery_status",
                        "start_line": line,
                        "arrival_monotonic_s": self._evidence_now(),
                        "context": self.sensor_context_snapshot(),
                        "assessment": result,
                    }
                )
                self.log.put((self.MSG_NORMAL, "Recovery " + json.dumps(result, allow_nan=False)))
                return result["allowed"]
            except (TypeError, ValueError) as error:
                self.log.put((self.MSG_ERROR, "Recovery: " + str(error)))
                return False

    def _evidence_now(self):
        return self._evidence_arrival_override if self._evidence_arrival_override is not None else time.monotonic()

    def sensor_context_snapshot(self):
        with self._adaptive_lock:
            context = self.run_evidence.snapshot(self._evidence_now())
            writer_status = self._evidence_writer.status() if self._evidence_writer else None
            context["recording"] = {
                "jsonl_path": str(self.sensor_log_path) if self.sensor_log_path else None,
                "write_failed": self._adaptive_log_failed or bool(writer_status and writer_status.get("error")),
                "session_limit_bytes": MAX_EVIDENCE_LOG_BYTES,
                "retained_frames": len(self.run_evidence.history),
                "retention_limit": self.run_evidence.history.maxlen,
                "journal": writer_status,
                "error": (writer_status or {}).get("error") or self._recording_last_error,
            }
            context["recovery_buffer"] = {
                "disposal_pending": self._recovery_disposal_nonce is not None,
                "firmware_acknowledged": self._recovery_disposal_ack,
                "next_action": "If halted, explicitly Unlock first; Abort retries disposal. Matching firmware RB acknowledgement and fresh Idle are required"
                if self._recovery_disposal_nonce is not None
                else None,
            }
            if self.measurement_context_provider:
                try:
                    declaration = deepcopy(self.measurement_context_provider())
                except Exception as error:
                    declaration = None
                    context["measurement_declarations_error"] = str(error)
                if isinstance(declaration, dict):
                    # Explicit physical declarations remain distinct from measurements.
                    context["measurement_declarations"] = declaration.copy()
                    context["tool_assembly_id"] = declaration.get("assembly_id")
                    context["seating_revision"] = declaration.get("seat_revision")
                    for key in (
                        "assembly_id",
                        "assembly_revision_id",
                        "assignment_id",
                        "seat_revision",
                        "probe_identity",
                        "configuration_id",
                    ):
                        context[key] = declaration.get(key)
            return context

    def set_program_source(self, path, lines=None):
        with self._adaptive_lock:
            program = self.run_evidence.set_program(path, lines)
            self._write_evidence(
                {
                    "schema": "carvera.run.v1",
                    "kind": "program_manifest",
                    "arrival_monotonic_s": self._evidence_now(),
                    "data": program,
                },
                background=True,
            )
            return program

    def _program_request(self, filename, action):
        if self.run_evidence.program:
            self.run_evidence.program["requested_machine_path"] = str(filename)
            self.run_evidence.program["request"] = action
            # A local hash never establishes the SD-card bytes selected for playback.
            self.run_evidence.program["machine_file_identity"] = "unverified"

    def _write_evidence(self, record, *, background=False):
        with self._adaptive_lock:
            return self._write_evidence_unlocked(record, background=background)

    def _write_evidence_unlocked(self, record, *, background=False):
        from .machine.evidence_io import BoundedJournalWriter, append_jsonl

        if not self._evidence_writes_enabled:
            return True
        if self._adaptive_log_failed:
            return False
        try:
            if self.sensor_log_path is None:
                folder = Path(os.environ.get("KIVY_HOME", str(Path.home() / ".kivy"))) / "sensor-evidence"
                folder.mkdir(parents=True, exist_ok=True)
                self.sensor_log_path = folder / (
                    datetime.now(timezone.utc).strftime("telemetry-%Y%m%dT%H%M%S.%f")
                    + f"-{os.getpid()}-{id(self):x}.jsonl"
                )
            if self._evidence_writer is None:
                self._evidence_writer = BoundedJournalWriter(
                    self.sensor_log_path,
                    max_bytes=MAX_EVIDENCE_LOG_BYTES,
                    max_line_bytes=2 * 1024 * 1024,
                    max_pending_bytes=4 * 1024 * 1024,
                )
            if background:
                accepted = self._evidence_writer.submit(record)
                state = self._evidence_writer.status()
                if not accepted:
                    error = (
                        state.get("error")
                        or state.get("last_submission_error")
                        or "Evidence queue full; dropped record is counted"
                    )
                    if error != self._recording_last_error:
                        self.log.put((self.MSG_ERROR, str(error)))
                    self._recording_last_error = str(error)
                    self._adaptive_log_failed = bool(state.get("error"))
                return accepted
            if not self._evidence_writer.flush(timeout_s=0.5):
                self._recording_last_error = (
                    "Evidence not durable yet: writer busy or failed; operator change not saved"
                )
                self._adaptive_log_failed = bool(self._evidence_writer.status().get("error"))
                self.log.put((self.MSG_ERROR, self._recording_last_error))
                return False
            receipt = append_jsonl(self.sensor_log_path, record, max_bytes=MAX_EVIDENCE_LOG_BYTES)
            self._recording_last_error = None
            self._last_operator_evidence_receipt = receipt
            return True
        except (OSError, ValueError) as error:
            self._adaptive_log_failed = True
            self._recording_last_error = str(error)
            self.log.put((self.MSG_ERROR, "Adaptive logging disabled: " + str(error)))
            return False

    def shutdown_evidence(self):
        """Stop recorder admission and preserve unfinished records on application exit."""
        from .machine.evidence_io import write_json_atomic

        with self._adaptive_lock:
            if self._evidence_writer is None:
                return True
            if self._evidence_writer.close(timeout_s=0.5):
                return True
            pending = self._evidence_writer.pending_records()
            if not pending:
                return False
            path = Path(str(self.sensor_log_path) + f".pending-exit-{time.time_ns()}.json")
            try:
                receipt = write_json_atomic(
                    path,
                    {
                        "schema": "carvera.pending-evidence.v1",
                        "records": pending,
                        "old_journal": str(self.sensor_log_path),
                        "writer_status": self._evidence_writer.status(),
                        "basis": "pending exit forensic records; not successful journal append",
                    },
                    max_bytes=8 * 1024 * 1024,
                )
                self._last_pending_evidence_receipt = {"path": str(path), "receipt": receipt}
                self.log.put((self.MSG_ERROR, "Recorder unfinished; pending evidence preserved at " + str(path)))
            except (OSError, ValueError) as error:
                self.log.put((self.MSG_ERROR, "Pending evidence could not be preserved on exit: " + str(error)))
            return False

    def evidenceCommand(self, command):
        """Local recorder/replay commands; never forwarded as G-code."""
        from .machine.evidence_io import write_json_atomic
        from .session_replay import replay_jsonl

        parts = command.split(maxsplit=2)
        action = parts[1].lower() if len(parts) > 1 else "status"
        with self._adaptive_lock:
            try:
                if action == "status":
                    result = self.sensor_context_snapshot()
                elif action == "restart" and len(parts) == 2:
                    old_path = self.sensor_log_path
                    old_state = self._evidence_writer.status() if self._evidence_writer else None
                    pending_receipt = None
                    if self._evidence_writer:
                        flushed = self._evidence_writer.flush(timeout_s=0.5)
                        if not flushed and not self._evidence_writer.status().get("error"):
                            raise ValueError("Recorder is still writing; wait for its receipt before restarting")
                        self._evidence_writer.close(timeout_s=0)
                        pending = self._evidence_writer.pending_records()
                        if pending:
                            # Preserve rejected/torn-write records in a fresh,
                            # durable sidecar before releasing their RAM custody.
                            pending_path = Path(str(old_path) + f".pending-{time.time_ns()}.json")
                            pending_receipt = {
                                "path": str(pending_path),
                                "receipt": write_json_atomic(
                                    pending_path,
                                    {
                                        "schema": "carvera.pending-evidence.v1",
                                        "records": pending,
                                        "old_journal": str(old_path),
                                        "writer_status": old_state,
                                        "basis": "pending forensic records; not successful journal append",
                                    },
                                    max_bytes=8 * 1024 * 1024,
                                ),
                            }
                    self._evidence_writer = None
                    self.sensor_log_path = None
                    self._adaptive_log_failed = False
                    self._recording_last_error = None
                    restart = {
                        "schema": "carvera.run.v1",
                        "kind": "recording_restart",
                        "arrival_monotonic_s": self._evidence_now(),
                        "old_journal": str(old_path),
                        "old_writer_status": old_state,
                        "pending_preserved": pending_receipt,
                    }
                    if not self._write_evidence(restart):
                        raise ValueError("New recorder could not establish a durable restart receipt")
                    result = {"restarted": str(self.sensor_log_path), "pending_preserved": pending_receipt}
                elif action == "export" and len(parts) == 3:
                    path = Path(parts[2]).expanduser()
                    if self.sensor_log_path and (
                        path.resolve() == Path(self.sensor_log_path).resolve()
                        or (
                            path.exists()
                            and Path(self.sensor_log_path).exists()
                            and path.samefile(self.sensor_log_path)
                        )
                    ):
                        raise ValueError("Export destination cannot replace the live evidence journal")
                    result = {
                        "schema": "carvera.run.export.v1",
                        "snapshot": self.sensor_context_snapshot(),
                        "pending_records": self._evidence_writer.pending_records() if self._evidence_writer else [],
                        "pending_records_basis": "Queued or failed records; this export does not prove journal durability",
                        "events": list(self.run_evidence.events),
                        "frames": list(self.run_evidence.history),
                    }
                    receipt = write_json_atomic(path, result)
                    result = {"saved_and_read_back": str(path), "receipt": receipt}
                elif action == "replay" and len(parts) == 3:
                    result = replay_jsonl(parts[2])
                else:
                    raise ValueError("Local commands: evidence status / restart / export <path> / replay <jsonl>")
                self.log.put((self.MSG_NORMAL, "Evidence " + json.dumps(result, allow_nan=False)))
                return True
            except (OSError, ValueError) as error:
                self.log.put((self.MSG_ERROR, "Evidence: " + str(error)))
                return False

    def machine_response_age(self, now):
        """Receive-thread liveness, independent of UI scheduling and wall-clock jumps."""
        with self._adaptive_lock:
            timestamp = self._last_status_received_at
            if timestamp is None:
                timestamp = self._connection_started_at
            if self.stream is None or timestamp is None:
                return None
            if not math.isfinite(now) or now < timestamp:
                return math.inf
            return now - timestamp

    def receive_diagnostics(self, now=None):
        """Detached observations across reconnects, independent of readiness."""
        from copy import deepcopy

        with self._adaptive_lock:
            return {
                "current": self._receive_health.snapshot(time.monotonic() if now is None else now),
                "recent_losses": deepcopy(list(self._receive_losses)),
            }

    def record_receive_loss(self, now):
        """Freeze the watchdog's evidence before reconnect resets the receiver."""
        with self._adaptive_lock:
            if (
                self._receive_losses
                and self._receive_losses[-1]["connection_generation"] == self._connection_generation
            ):
                return
            self._receive_losses.append(
                {
                    **self._receive_health.snapshot(now),
                    "observed_at": datetime.now(timezone.utc).isoformat(),
                    "reason": "No valid machine status within watchdog timeout",
                }
            )
            self.log.put((self.MSG_NORMAL, "Receive watchdog evidence: " + json.dumps(self._receive_losses[-1])))

    def streamIO(self, generation=None):
        if generation is None:
            generation = self._connection_generation
        self.sio_status = False
        self.sio_diagnose = False
        dynamic_delay = 0.1
        tr = td = time.monotonic()
        health = self._receive_health
        last_error = ""

        while not self.stop.is_set():
            with self._adaptive_lock:
                if generation != self._connection_generation:
                    return
                self.adaptive_monitor.tick(time.monotonic())
            health.stage("loop", time.monotonic(), loop=True)
            if not self.stream or self.paused:
                health.stage("paused", time.monotonic())
                self._stream_io_parked = True
                # Short sleep so baud-switch / file-transfer pause ends promptly.
                time.sleep(0.05)
                continue
            self._stream_io_parked = False
            t = time.monotonic()
            # refresh machine position?
            running = self.sendNUM > 0 or self.loadNUM > 0 or self.pausing
            try:
                if not running and self.protocol_ready:
                    if self._status_poll_requested or t - tr > STREAM_POLL:
                        health.stage("status poll", time.monotonic())
                        self.viewStatusReport(True)
                        with self._adaptive_lock:
                            if generation != self._connection_generation:
                                return
                            self._status_poll_requested = False
                        tr = t
                    if (
                        self.sio_diagnose
                        and self._diagnose_requested_at is not None
                        and self._evidence_now() - self._diagnose_requested_at > BACKGROUND_DIAGNOSE_POLL
                    ):
                        self.sio_diagnose = False
                    diagnose_interval = DIAGNOSE_POLL if self.diagnosing else BACKGROUND_DIAGNOSE_POLL
                    if not self.sio_diagnose and t - td > diagnose_interval:
                        self.viewDiagnoseReport(True)
                        td = t
                    if self._fault_dump_pending and self.run_evidence.latest and not self.status_reacquisition_pending:
                        fault = self.run_evidence.latest.get("fault")
                        if fault:
                            if self.executeCommand("M964\n"):
                                self._last_fault_dump_requested = int(fault[0])
                                self._fault_dump_pending = False
                    previous = self.run_evidence.latest.get("previous_fault") if self.run_evidence.latest else None
                    if previous and previous[3] and not self.status_reacquisition_pending:
                        identity = (int(previous[0]), int(previous[1]))
                        if identity != self._last_previous_fault_dump_requested and self.executeCommand("M964 L1\n"):
                            self._last_previous_fault_dump_requested = identity
                else:
                    tr = t
                    td = t

                stream = self.stream
                health.stage("waiting for bytes", time.monotonic())
                if stream.waiting_for_recv():
                    health.stage("receiving bytes", time.monotonic())
                    data = stream.recv()
                    if data:
                        health.wire(len(data), time.monotonic())
                        with self._adaptive_lock:
                            if generation != self._connection_generation or stream is not self.stream:
                                return
                            allow_wire_switch = self.sendNUM == 0 and self.loadNUM == 0
                            health.stage("parsing bytes", time.monotonic())
                            for message in self.comms.feed(data, allow_wire_switch=allow_wire_switch):
                                self._handle_protocol_message(message)
                    dynamic_delay = 0
                else:
                    if self.sendNUM == 0 and self.loadNUM == 0:
                        dynamic_delay = 0.1 if dynamic_delay >= 0.09 else dynamic_delay + 0.01
                    else:
                        dynamic_delay = 0

            except Exception as error:
                with self._adaptive_lock:
                    if generation != self._connection_generation:
                        return
                    self.comms.reset_parser()
                health.error(error, time.monotonic())
                # A readable EOF/socket fault otherwise spins at full CPU until
                # the watchdog disconnects. Preserve stale status and back off.
                dynamic_delay = 0.1
                exc_msg = str(sys.exc_info()[1])
                if self._baud_switch_in_progress:
                    last_error = exc_msg
                    continue
                if last_error != exc_msg:
                    self.log.put((Controller.MSG_ERROR, exc_msg))
                    last_error = exc_msg

            if dynamic_delay > 0:
                health.stage("poll interval", time.monotonic())
                time.sleep(dynamic_delay)

    def parseWCSParameters(self, line):
        """Parse WCS parameters from machine response"""
        # Parse format: [G54:-123.6800,-123.6800,-123.6800,-50,0.000,25.123]
        # Extract all WCS entries from the line

        # parse the current WCS from the "get wcs" command
        get_wcs_pattern = r"\[current WCS: (G5[4-9][.1-3]*)\]"
        current_wcs_matches = re.findall(get_wcs_pattern, line)

        if current_wcs_matches:
            # if not on community firmware or rotation angle is not set,
            # the active coordinate system is tracked through the "get wcs" command
            if not self.is_community_firmware or not CNC.can_rotate_wcs:
                CNC.vars["active_coord_system"] = CNC.wcs_names.index(current_wcs_matches[0])
            return

        wcs_pattern = r"\[(G5[4-9][.1-3]*):([^]]+)\]"
        matches = re.findall(wcs_pattern, line)
        wcs_data = {}
        for wcs_code, values_str in matches:
            # Split the values by comma
            values = values_str.split(",")
            if len(values) >= 5:  # X, Y, Z, A, B, Rotation
                try:
                    x = float(values[0])
                    y = float(values[1])
                    z = float(values[2])
                    a = float(values[3])
                    b = float(values[4])  # B is always 0
                    if self.is_community_firmware and CNC.can_rotate_wcs:
                        rotation = float(values[5])
                    else:
                        rotation = 0.0
                    wcs_data[wcs_code] = [x, y, z, a, b, rotation]  # Store only X, Y, Z, A, B, Rotation

                except (ValueError, IndexError):
                    logger.error(f"Error parsing WCS values for {wcs_code}: {values_str}")

        # Send the parsed data to the WCS Settings popup if it's open
        if hasattr(self, "wcs_popup_callback") and self.wcs_popup_callback:
            self.wcs_popup_callback(wcs_data)
