# copyright (c) 2018- polygoniq xyz s.r.o.

import bpy
import bpy_extras.io_utils
import io
import os
import math
import datetime
import typing
import urllib.error
import urllib.request
import re

from . import log_helpers_bpy
from . import utils_bpy
from . import ui_bpy

if typing.TYPE_CHECKING:
    from bpy._typing import rna_enums

# Discord has a limit of 10 files per message, but we want to limit the memory usage (+1 for logs)
# Also, Google Cloud Run has a request size limit of 32MB
MAX_FILE_ATTACHMENTS = 3
MAX_FILE_SIZE_BYTES = 8 * 1024 * 1024  # 8MB - Discord webhook limit for default servers
# Discord has a limit of 2000 characters per message
# We set a lower limit so there is room for the contact info + message formatting
MAX_TOTAL_DESCRIPTION_CHARACTERS = 1800
MAX_TOTAL_SUMMARY_CHARACTERS = 80  # Arbitrary limit to encourage concise summaries

TIMEOUT_SECONDS = 30
COOLDOWN_SECONDS = 30

# Used for storing a global info accessible from all addons' polibs
NEXT_REPORT_TIMESTAMP_KEY = "pq_bug_report_next_timestamp"
USER_EMAIL_KEY = "pq_bug_report_user_email"
USER_DISCORD_KEY = "pq_bug_report_user_discord"

EMAIL_REGEX = re.compile(r"[^@]+@[^@]+\.[^@]+")

EXT_MAPPINGS = {
    ".txt": 'TEXT',
    ".md": 'TEXT',
    ".zip": 'FILE',
    ".tar.gz": 'FILE',
    # Images
    ".jpg": 'FILE_IMAGE',
    ".jpeg": 'FILE_IMAGE',
    ".png": 'FILE_IMAGE',
    ".bmp": 'FILE_IMAGE',
    # 3D / CGI
    ".blend": 'FILE_BLEND',
    ".obj": 'FILE_3D',
    ".fbx": 'FILE_3D',
    ".gltf": 'FILE_3D',
    # Motion picture
    ".mp4": 'FILE_MOVIE',
    ".mov": 'FILE_MOVIE',
    ".avi": 'FILE_MOVIE',
    ".mkv": 'FILE_MOVIE',
    ".gif": 'FILE_MOVIE',
}

# Derived glob pattern used by the file browser to show only allowed extensions.
_ALLOWED_EXTENSIONS_GLOB = ";".join(f"*{ext}" for ext in EXT_MAPPINGS)


API_VERSION = "v1"
BUG_REPORT_APP_URL = f"https://extensions-extras.polygoniq.com/{API_VERSION}/bug-report"


CONTACT_COLLECTION_INFO = """Providing your contact information (email and/or Discord) is optional but highly recommended,
as it allows us to reach out to you for more details if needed and to notify you when the bug is fixed."""

LOG_COLLECTION_INFO = """Logs contain information about your machine, OS, Blender version, and the actions you took leading up to the bug.
They help us to better understand the context of the bug and are crucial for us to be able to fix it."""

STORAGE_INFO = """This information will be stored in a private Discord channel only accessible to the Polygoniq team
and will be deleted as soon as the bug is resolved or after a maximum of 2 years.
You may contact us in order to have them deleted sooner."""


class MultipartBodyReader(io.RawIOBase):
    """Streaming multipart/form-data body reader.

    Builds the multipart body lazily: text field parts are stored as pre-encoded bytes;
    file parts are opened just-in-time when the reader reaches them and closed immediately
    after. This avoids loading all file contents into memory at once.
    """

    def __init__(
        self,
        boundary: str,
        text_fields: dict[str, str],
        file_tuples: list[tuple[str, str, str]],
    ) -> None:
        # Each segment is either bytes (boundary/header/text) or a str filepath (file content).
        self._segments: list[bytes | str] = []
        for key, value in text_fields.items():
            self._segments.append(
                f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode()
            )
        for field_name, filename, filepath in file_tuples:
            self._segments.append(
                f'--{boundary}\r\nContent-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()
            )
            self._segments.append(filepath)
            self._segments.append(b'\r\n')
        self._segments.append(f'--{boundary}--\r\n'.encode())

        self._seg_index: int = 0
        self._seg_offset: int = 0
        self._current_file: typing.BinaryIO | None = None

    def __len__(self) -> int:
        total = 0
        for seg in self._segments:
            if isinstance(seg, bytes):
                total += len(seg)
            else:
                total += os.path.getsize(seg)
        return total

    def readable(self) -> bool:
        return True

    def readinto(self, b: bytearray) -> int:  # type: ignore[override]
        written = 0
        while written < len(b) and self._seg_index < len(self._segments):
            seg = self._segments[self._seg_index]
            if isinstance(seg, bytes):
                chunk = seg[self._seg_offset : self._seg_offset + len(b) - written]
                n = len(chunk)
                b[written : written + n] = chunk
                written += n
                self._seg_offset += n
                if self._seg_offset >= len(seg):
                    self._seg_index += 1
                    self._seg_offset = 0
            else:
                if self._current_file is None:
                    self._current_file = open(seg, "rb")
                chunk = self._current_file.read(len(b) - written)
                if len(chunk) == 0:
                    self._current_file.close()
                    self._current_file = None
                    self._seg_index += 1
                    self._seg_offset = 0
                    continue
                b[written : written + len(chunk)] = chunk
                written += len(chunk)
        return written

    def close(self) -> None:
        if self._current_file is not None:
            self._current_file.close()
            self._current_file = None
        super().close()


def get_cooldown_remaining_seconds() -> int:
    next_timestamp: datetime.datetime | None = bpy.app.driver_namespace.get(
        NEXT_REPORT_TIMESTAMP_KEY
    )
    if next_timestamp is None:
        return 0
    now = datetime.datetime.now()
    difference = next_timestamp - now
    if difference.total_seconds() < 0:
        return 0
    return math.ceil(difference.total_seconds())


def _cooldown_redraw_timer() -> float | None:
    """Timer callback that forces a UI redraw every second while cooldown is active."""
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'PREFERENCES':
                area.tag_redraw()
    cooldown_remaining = get_cooldown_remaining_seconds()
    return 1.0 if cooldown_remaining > 0 else None


class ReportBugOperatorBase(bpy.types.Operator):
    bl_label = "Report a Bug"
    bl_description = "Report a bug to the Polygoniq team"
    bl_options = {'REGISTER'}

    # Email and Discord are stored globally
    email: bpy.props.StringProperty(
        name="Your Email",
        description="Your email address",
        get=lambda self: bpy.app.driver_namespace.get(USER_EMAIL_KEY, ""),
        set=lambda self, value: bpy.app.driver_namespace.__setitem__(USER_EMAIL_KEY, value),
    )

    discord: bpy.props.StringProperty(
        name="Your Discord",
        description="Your Discord handle",
        get=lambda self: bpy.app.driver_namespace.get(USER_DISCORD_KEY, ""),
        set=lambda self, value: bpy.app.driver_namespace.__setitem__(USER_DISCORD_KEY, value),
    )

    # Title and description are stored per addon and cleared on successful submission
    title: bpy.props.StringProperty(
        name="Title",
        description="Provide a brief summary of the bug you encountered",
        get=lambda self: getattr(type(self), "_title", ""),
        set=lambda self, value: setattr(type(self), "_title", value),
        options={'TEXTEDIT_UPDATE'},
    )

    description: bpy.props.StringProperty(
        name="Bug Description",
        description="Describe the bug you encountered in as much detail as possible, including steps to reproduce it, if you can",
        get=lambda self: getattr(type(self), "_description", ""),
        set=lambda self, value: setattr(type(self), "_description", value),
        options={'TEXTEDIT_UPDATE'},
    )

    include_logs: bpy.props.BoolProperty(
        name="Include Logs",
        description="Include logs in the bug report",
        default=True,
        get=lambda self: getattr(type(self), "_include_logs", True),
        set=lambda self, value: setattr(type(self), "_include_logs", value),
    )

    telemetry = None  # Type hinting this is quite problematic
    addon_name: str = ""
    add_file_attachments_operator: type[bpy.types.Operator] | None = None
    remove_file_attachment_operator: type[bpy.types.Operator] | None = None
    show_popup_operator: type[ui_bpy.ShowPopupBase] | None = None
    collected_filepaths: set[str] = set()

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return get_cooldown_remaining_seconds() == 0

    def invoke(
        self, context: bpy.types.Context, event: bpy.types.Event
    ) -> set["rna_enums.OperatorReturnItems"]:
        self._validate_class_members()
        return context.window_manager.invoke_props_dialog(self, width=600)

    @utils_bpy.blender_cursor('WAIT')
    def execute(self, context: bpy.types.Context) -> set["rna_enums.OperatorReturnItems"]:
        self._validate_class_members()
        telemetry = type(self).telemetry

        if self.email != "" and not EMAIL_REGEX.fullmatch(self.email):
            self.report({'ERROR'}, "Please enter a valid email address")
            return {'CANCELLED'}

        if self.title == "":
            self.report({'ERROR'}, "Please provide a title summarizing the bug")
            return {'CANCELLED'}

        if len(self.title) > MAX_TOTAL_SUMMARY_CHARACTERS:
            self.report(
                {'ERROR'},
                f"Summary is too long by {len(self.title) - MAX_TOTAL_SUMMARY_CHARACTERS} characters",
            )
            return {'CANCELLED'}

        if self.description == "":
            self.report({'ERROR'}, "Please provide a description of the bug")
            return {'CANCELLED'}

        if len(self.description) > MAX_TOTAL_DESCRIPTION_CHARACTERS:
            self.report(
                {'ERROR'},
                f"Description is too long by {len(self.description) - MAX_TOTAL_DESCRIPTION_CHARACTERS} characters",
            )
            return {'CANCELLED'}

        collected_logs = set()
        if self.include_logs:
            packed_logs_path = os.path.join(
                log_helpers_bpy.pack_logs(telemetry), "polygoniq_logs.zip"
            )
            if os.path.getsize(packed_logs_path) > MAX_FILE_SIZE_BYTES:
                self.report(
                    {'ERROR'},
                    "Logs are too large to attach. Please pack them manually and send them to us through another method",
                )
                return {'CANCELLED'}

            collected_logs.add(packed_logs_path)

        collected_filepaths = type(self).collected_filepaths
        data = {
            "addon_name": type(self).addon_name,
            "email": self.email,
            "discord": self.discord,
            "title": self.title,
            "description": self.description,
        }
        file_tuples = [
            (f"file_{i}", os.path.basename(filepath), filepath)
            for i, filepath in enumerate(collected_filepaths | collected_logs)
        ]
        boundary = os.urandom(16).hex()
        with MultipartBodyReader(boundary, data, file_tuples) as reader:
            try:
                req = urllib.request.Request(
                    BUG_REPORT_APP_URL,
                    data=reader,
                    headers={
                        'Content-Type': f'multipart/form-data; boundary={boundary}',
                        'Content-Length': str(len(reader)),
                        'User-Agent': 'polygoniq-bug-reporter/1.0',
                    },
                    method='POST',
                )
                try:
                    urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS)
                except urllib.error.HTTPError as e:
                    body = e.read().decode("utf-8", errors="replace")
                    raise RuntimeError(f"HTTP {e.code}: {body}") from e
                finally:
                    bpy.app.driver_namespace[NEXT_REPORT_TIMESTAMP_KEY] = (
                        datetime.datetime.now() + datetime.timedelta(seconds=COOLDOWN_SECONDS)
                    )
                    bpy.app.timers.register(_cooldown_redraw_timer)

                self.report({'INFO'}, "Bug report sent successfully!")
                # Only clear the content after a successful submission
                # to avoid making the user re-enter everything if the submission fails
                self._clear_content()
                return {'FINISHED'}
            except Exception as e:
                self.report({'ERROR'}, f"Failed to send bug report: {e}")
                return {'CANCELLED'}

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        layout.prop(self, "email", placeholder="example@example.com")
        if self.email != "" and not EMAIL_REGEX.match(self.email):
            row = layout.row()
            row.alert = True
            row.label(text="Please enter a valid email address", icon='ERROR')

        layout.prop(self, "discord", placeholder="YourDiscord")
        row = layout.row()
        row.alignment = 'LEFT'
        row.label(
            text="If you do not provide an email or discord, we won't be able to reach out to you",
            icon='INFO',
        )
        row.operator(
            "wm.url_open",
            text="Join our Discord",
            icon_value=ui_bpy.icon_manager.get_icon_id("logo_discord"),
        ).url = ui_bpy.SocialMediaURL.DISCORD

        op = row.operator(
            type(self).show_popup_operator.bl_idname,
            text="",
            icon='QUESTION',
        )
        op.title = "Sending Contact Information with Your Bug Report"
        op.message = CONTACT_COLLECTION_INFO + "\n\n" + STORAGE_INFO
        op.icon = 'QUESTION'

        col = layout.column(align=True)
        row = col.row()
        row.label(text="Title:")
        row = row.row()
        row.alignment = 'RIGHT'
        row.alert = len(self.title) > MAX_TOTAL_SUMMARY_CHARACTERS
        row.label(
            text=f"{len(self.title)}/{MAX_TOTAL_SUMMARY_CHARACTERS} characters",
        )
        col.row().prop(self, "title", text="")

        error_msg = None
        if self.title == "":
            error_msg = "Please provide a title summarizing the bug"
        if len(self.title) > MAX_TOTAL_SUMMARY_CHARACTERS:
            error_msg = f"Summary is too long by {len(self.title) - MAX_TOTAL_SUMMARY_CHARACTERS} characters"
        if error_msg is not None:
            row = col.row()
            row.alert = True
            row.label(text=error_msg, icon='ERROR')

        col = layout.column(align=True)
        row = col.row()
        row.label(text="Bug Description:")
        row = row.row()
        row.alignment = 'RIGHT'
        row.alert = len(self.description) > MAX_TOTAL_DESCRIPTION_CHARACTERS
        row.label(
            text=f"{len(self.description)}/{MAX_TOTAL_DESCRIPTION_CHARACTERS} characters",
        )
        if bpy.app.version >= (5, 2, 0):
            col.row().textbox(self, "description")
        else:
            col.row().prop(self, "description", text="")

        error_msg = None
        if self.description == "":
            error_msg = "Please provide a description of the bug"
        if len(self.description) > MAX_TOTAL_DESCRIPTION_CHARACTERS:
            error_msg = f"Description is too long by {len(self.description) - MAX_TOTAL_DESCRIPTION_CHARACTERS} characters"
        if error_msg is not None:
            row = col.row()
            row.alert = True
            row.label(text=error_msg, icon='ERROR')

        row = layout.row()
        row.prop(self, "include_logs", text="")
        row.label(text="Include logs (highly recommended)")
        op = row.operator(
            type(self).show_popup_operator.bl_idname,
            text="",
            icon='QUESTION',
        )
        op.title = "Sending Logs with Your Bug Report"
        op.message = LOG_COLLECTION_INFO + "\n\n" + STORAGE_INFO
        op.icon = 'QUESTION'

        layout.operator(
            type(self).add_file_attachments_operator.bl_idname,
            text=f"Add File Attachments ({MAX_FILE_ATTACHMENTS - len(type(self).collected_filepaths)} slots remaining)",
            icon='FILE_FOLDER',
        )

        for filepath in sorted(type(self).collected_filepaths):
            basename = os.path.basename(filepath)
            ext = os.path.splitext(basename)[1].lower()
            row = layout.row()
            row.label(text=os.path.basename(filepath), icon=EXT_MAPPINGS.get(ext, 'FILE_BLANK'))
            row.operator(
                type(self).remove_file_attachment_operator.bl_idname, text="", icon='X'
            ).filepath = filepath

    def _validate_class_members(self):
        assert type(self).telemetry is not None
        assert type(self).addon_name != ""
        assert type(self).add_file_attachments_operator is not None
        assert type(self).remove_file_attachment_operator is not None
        assert type(self).show_popup_operator is not None

    def _clear_content(self):
        self.title = ""
        self.description = ""
        self.include_logs = True
        type(self).collected_filepaths.clear()


class AddBugReportFileAttachmentsOperatorBase(bpy.types.Operator, bpy_extras.io_utils.ImportHelper):
    bl_label = f"Add File Attachments"
    bl_description = f"Add a file attachment to the bug report (Max {MAX_FILE_ATTACHMENTS} attachments, {utils_bpy.convert_size(MAX_FILE_SIZE_BYTES, decimal_places=0)} per file)"
    bl_options = {'REGISTER'}

    # Required for multi-file selection
    directory: bpy.props.StringProperty(subtype='DIR_PATH')
    files: bpy.props.CollectionProperty(type=bpy.types.OperatorFileListElement)
    filter_glob: bpy.props.StringProperty(default=_ALLOWED_EXTENSIONS_GLOB, options={'HIDDEN'})

    bug_report_operator: type[bpy.types.Operator] | None = None

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        assert cls.bug_report_operator is not None
        return len(cls.bug_report_operator.collected_filepaths) < MAX_FILE_ATTACHMENTS

    def execute(self, context: bpy.types.Context) -> set["rna_enums.OperatorReturnItems"]:
        bug_report_operator = type(self).bug_report_operator
        assert bug_report_operator is not None and hasattr(
            bug_report_operator, "collected_filepaths"
        )
        selected_filepaths = {
            os.path.join(self.directory, file_elem.name) for file_elem in self.files
        }
        all_filepaths = bug_report_operator.collected_filepaths | selected_filepaths
        if len(all_filepaths) > MAX_FILE_ATTACHMENTS:
            self.report(
                {'ERROR'},
                f"Cannot attach more than {MAX_FILE_ATTACHMENTS} file attachments in total",
            )
            return {'CANCELLED'}

        duplicate_filepaths = set()
        for filepath in selected_filepaths:
            if not os.path.isfile(filepath):
                self.report({'ERROR'}, f"File not found: {filepath}")
                continue
            ext = os.path.splitext(filepath)[1].lower()
            if ext not in EXT_MAPPINGS:
                self.report({'ERROR'}, f"File type '{ext}' is not allowed as an attachment")
                continue
            size = os.path.getsize(filepath)
            if size > MAX_FILE_SIZE_BYTES:
                self.report(
                    {'ERROR'},
                    f"File is too large: {filepath}. Max allowed size is {utils_bpy.convert_size(MAX_FILE_SIZE_BYTES, decimal_places=0)}",
                )
                continue
            if filepath in bug_report_operator.collected_filepaths:
                duplicate_filepaths.add(f"'{filepath}'")
                continue
            bug_report_operator.collected_filepaths.add(filepath)

        if len(duplicate_filepaths) > 0:
            self.report(
                {'WARNING'},
                f"The following files were already attached and were not added again: {', '.join(duplicate_filepaths)}",
            )
        return {'FINISHED'}


class RemoveBugReportFileAttachmentOperatorBase(bpy.types.Operator):
    bl_label = "Remove File Attachment"
    bl_description = "Remove a file attachment from the bug report"
    bl_options = {'REGISTER'}

    filepath: bpy.props.StringProperty()
    bug_report_operator: type[bpy.types.Operator] | None = None

    def execute(self, context: bpy.types.Context) -> set["rna_enums.OperatorReturnItems"]:
        bug_report_operator = type(self).bug_report_operator
        assert bug_report_operator is not None and hasattr(
            bug_report_operator, "collected_filepaths"
        )
        if self.filepath in bug_report_operator.collected_filepaths:
            bug_report_operator.collected_filepaths.remove(self.filepath)
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, "Filepath not found in attachments.")
            return {'CANCELLED'}


def bug_report_operators_factory(
    bl_idname_addon_prefix: str,
    telemetry,
    show_popup_operator: type[ui_bpy.ShowPopupBase],
) -> tuple[
    type[ReportBugOperatorBase],
    type[AddBugReportFileAttachmentsOperatorBase],
    type[RemoveBugReportFileAttachmentOperatorBase],
]:
    """Factory function to create operators for bug reporting and adding and removing file attachments.

    Args:
        bl_idname_addon_prefix: The prefix for the `bl_idname` of the operators. (e.g. "engon")
        telemetry: The telemetry instance to be used by the ReportBugOperator.
        show_popup_operator: The operator class to be used for showing popups.
    Returns a tuple of:
        - ReportBugOperator class
        - AddFileAttachmentsOperator class
        - RemoveFileAttachmentOperator class
    """

    report_bug_op = log_helpers_bpy.logged_operator(
        type(
            f"ReportBug{bl_idname_addon_prefix.capitalize()}",
            (ReportBugOperatorBase,),
            {
                "bl_idname": f"{bl_idname_addon_prefix}.report_bug",
            },
        )
    )

    add_file_attachments_op = log_helpers_bpy.logged_operator(
        type(
            f"AddFileAttachments{bl_idname_addon_prefix.capitalize()}",
            (AddBugReportFileAttachmentsOperatorBase,),
            {
                "bl_idname": f"{bl_idname_addon_prefix}.bug_report_add_file_attachments",
                "bug_report_operator": report_bug_op,
            },
        )
    )

    remove_file_attachment_op = log_helpers_bpy.logged_operator(
        type(
            f"RemoveFileAttachment{bl_idname_addon_prefix.capitalize()}",
            (RemoveBugReportFileAttachmentOperatorBase,),
            {
                "bl_idname": f"{bl_idname_addon_prefix}.bug_report_remove_file_attachment",
                "bug_report_operator": report_bug_op,
            },
        )
    )

    report_bug_op.addon_name = bl_idname_addon_prefix
    report_bug_op.telemetry = telemetry
    report_bug_op.add_file_attachments_operator = add_file_attachments_op
    report_bug_op.remove_file_attachment_operator = remove_file_attachment_op
    report_bug_op.show_popup_operator = show_popup_operator

    return report_bug_op, add_file_attachments_op, remove_file_attachment_op
