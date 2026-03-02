from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import JSON

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

app = Flask(__name__, template_folder="app/templates", static_folder="app/static", static_url_path="/static")
app.config["SECRET_KEY"] = "ticketgest-dev"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///ticketgest.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


class RequestType(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    notification_emails = db.Column(db.Text, nullable=False, default="")

    def email_list(self) -> list[str]:
        return [email.strip() for email in self.notification_emails.split(",") if email.strip()]


class TicketClass(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    fields = db.relationship("FieldDefinition", backref="ticket_class", cascade="all, delete-orphan")


class FieldDefinition(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_class_id = db.Column(db.Integer, db.ForeignKey("ticket_class.id"), nullable=False)
    label = db.Column(db.String(120), nullable=False)
    key = db.Column(db.String(120), nullable=False)
    data_type = db.Column(db.String(20), nullable=False)  # string, numeric, text, date
    control_type = db.Column(db.String(30), nullable=False)  # textfield, textbox, combo, radio, multi
    options = db.Column(db.Text, nullable=True)
    required = db.Column(db.Boolean, nullable=False, default=False)

    def option_values(self) -> list[str]:
        if not self.options:
            return []
        return [option.strip() for option in self.options.split(",") if option.strip()]


class TicketTemplateAttachment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_class_id = db.Column(db.Integer, db.ForeignKey("ticket_class.id"), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False)


class TicketInstance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    access_path = db.Column(db.String(40), unique=True, nullable=False, default=lambda: uuid.uuid4().hex[:12])
    title = db.Column(db.String(180), nullable=False)
    status = db.Column(db.String(30), nullable=False, default="abierto")
    creator_email = db.Column(db.String(255), nullable=False)
    ticket_class_id = db.Column(db.Integer, db.ForeignKey("ticket_class.id"), nullable=False)
    request_type_id = db.Column(db.Integer, db.ForeignKey("request_type.id"), nullable=False)
    form_data = db.Column(JSON, nullable=False, default={})
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    ticket_class = db.relationship("TicketClass")
    request_type = db.relationship("RequestType")
    attachments = db.relationship("TicketInstanceAttachment", backref="ticket", cascade="all, delete-orphan")
    logs = db.relationship("TicketChangeLog", backref="ticket", cascade="all, delete-orphan")


class TicketInstanceAttachment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey("ticket_instance.id"), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False)


class TicketChangeLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey("ticket_instance.id"), nullable=False)
    actor_email = db.Column(db.String(255), nullable=False)
    action = db.Column(db.String(120), nullable=False)
    comment = db.Column(db.Text, nullable=True)
    previous_status = db.Column(db.String(30), nullable=True)
    new_status = db.Column(db.String(30), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    data_snapshot = db.Column(JSON, nullable=True)
    attachments = db.relationship("TicketLogAttachment", backref="log", cascade="all, delete-orphan")


class TicketLogAttachment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    log_id = db.Column(db.Integer, db.ForeignKey("ticket_change_log.id"), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False)


def save_upload(file_storage) -> tuple[str, str] | None:
    if not file_storage or not file_storage.filename:
        return None
    ext = Path(file_storage.filename).suffix
    stored_name = f"{uuid.uuid4().hex}{ext}"
    file_storage.save(UPLOAD_DIR / stored_name)
    return file_storage.filename, stored_name


def notify_status_change(ticket: TicketInstance, previous_status: str, new_status: str) -> None:
    recipients = set(ticket.request_type.email_list())
    recipients.add(ticket.creator_email)
    notification = {
        "timestamp": datetime.utcnow().isoformat(),
        "ticket_id": ticket.id,
        "path": ticket.access_path,
        "from": previous_status,
        "to": new_status,
        "recipients": sorted(recipients),
    }
    with open(BASE_DIR / "notification.log", "a", encoding="utf-8") as file:
        file.write(json.dumps(notification, ensure_ascii=False) + "\n")


@app.route("/")
def index():
    query = TicketInstance.query.order_by(TicketInstance.created_at.desc())
    status = request.args.get("status")
    request_type_id = request.args.get("request_type_id")
    ticket_class_id = request.args.get("ticket_class_id")
    creator = request.args.get("creator")

    if status:
        query = query.filter_by(status=status)
    if request_type_id:
        query = query.filter_by(request_type_id=request_type_id)
    if ticket_class_id:
        query = query.filter_by(ticket_class_id=ticket_class_id)
    if creator:
        query = query.filter(TicketInstance.creator_email.contains(creator.strip()))

    tickets = query.all()
    return render_template(
        "index.html",
        tickets=tickets,
        classes=TicketClass.query.order_by(TicketClass.name).all(),
        types=RequestType.query.order_by(RequestType.name).all(),
        filters={"status": status or "", "request_type_id": request_type_id or "", "ticket_class_id": ticket_class_id or "", "creator": creator or ""},
    )


@app.route("/tickets/new", methods=["GET", "POST"])
def create_ticket():
    classes = TicketClass.query.order_by(TicketClass.name).all()
    types = RequestType.query.order_by(RequestType.name).all()
    class_id = request.values.get("class_id", type=int)
    selected_class = TicketClass.query.get(class_id) if class_id else None

    if request.method == "POST" and selected_class:
        form_data = {}
        for field in selected_class.fields:
            value = request.form.getlist(field.key) if field.control_type == "multi" else request.form.get(field.key, "")
            if field.required and not value:
                flash(f"El campo {field.label} es obligatorio", "danger")
                return redirect(url_for("create_ticket", class_id=class_id))
            form_data[field.key] = value

        ticket = TicketInstance(
            title=request.form["title"],
            creator_email=request.form["creator_email"],
            ticket_class_id=selected_class.id,
            request_type_id=request.form.get("request_type_id", type=int),
            form_data=form_data,
        )
        db.session.add(ticket)
        db.session.flush()

        upload = save_upload(request.files.get("ticket_attachment"))
        if upload:
            db.session.add(TicketInstanceAttachment(ticket_id=ticket.id, original_filename=upload[0], stored_filename=upload[1]))

        db.session.add(
            TicketChangeLog(
                ticket_id=ticket.id,
                actor_email=ticket.creator_email,
                action="Creación",
                comment="Ticket creado",
                previous_status="",
                new_status=ticket.status,
                data_snapshot=form_data,
            )
        )
        db.session.commit()
        notify_status_change(ticket, "", ticket.status)
        flash(f"Ticket #{ticket.id} creado", "success")
        return redirect(url_for("view_ticket", access_path=ticket.access_path))

    templates = (
        TicketTemplateAttachment.query.filter_by(ticket_class_id=selected_class.id).all() if selected_class else []
    )
    return render_template(
        "ticket_form.html", classes=classes, types=types, selected_class=selected_class, templates=templates
    )


@app.route("/tickets/<access_path>", methods=["GET", "POST"])
def view_ticket(access_path: str):
    ticket = TicketInstance.query.filter_by(access_path=access_path).first_or_404()

    if request.method == "POST":
        previous_status = ticket.status
        new_status = request.form.get("new_status", ticket.status)
        actor = request.form["actor_email"]
        comment = request.form.get("comment", "")
        action = request.form.get("action", "Actualización")
        ticket.status = new_status

        log = TicketChangeLog(
            ticket_id=ticket.id,
            actor_email=actor,
            action=action,
            comment=comment,
            previous_status=previous_status,
            new_status=new_status,
            data_snapshot=ticket.form_data,
        )
        db.session.add(log)
        db.session.flush()

        ticket_upload = save_upload(request.files.get("ticket_attachment"))
        if ticket_upload:
            db.session.add(TicketInstanceAttachment(ticket_id=ticket.id, original_filename=ticket_upload[0], stored_filename=ticket_upload[1]))

        log_upload = save_upload(request.files.get("log_attachment"))
        if log_upload:
            db.session.add(TicketLogAttachment(log_id=log.id, original_filename=log_upload[0], stored_filename=log_upload[1]))

        db.session.commit()

        if previous_status != new_status:
            notify_status_change(ticket, previous_status, new_status)
        flash("Ticket actualizado", "success")
        return redirect(url_for("view_ticket", access_path=ticket.access_path))

    templates = TicketTemplateAttachment.query.filter_by(ticket_class_id=ticket.ticket_class_id).all()
    return render_template("ticket_detail.html", ticket=ticket, templates=templates)


@app.route("/admin", methods=["GET"])
def admin_panel():
    return render_template(
        "admin.html",
        classes=TicketClass.query.order_by(TicketClass.name).all(),
        types=RequestType.query.order_by(RequestType.name).all(),
    )


@app.route("/admin/request-types", methods=["POST"])
def create_request_type():
    req = RequestType(name=request.form["name"], notification_emails=request.form.get("notification_emails", ""))
    db.session.add(req)
    db.session.commit()
    flash("Tipo de solicitud creado", "success")
    return redirect(url_for("admin_panel"))


@app.route("/admin/ticket-classes", methods=["POST"])
def create_ticket_class():
    tc = TicketClass(name=request.form["name"], description=request.form.get("description", ""))
    db.session.add(tc)
    db.session.commit()
    flash("Clase de ticket creada", "success")
    return redirect(url_for("admin_panel"))


@app.route("/admin/ticket-classes/<int:class_id>/fields", methods=["POST"])
def create_field(class_id: int):
    field = FieldDefinition(
        ticket_class_id=class_id,
        label=request.form["label"],
        key=request.form["key"],
        data_type=request.form["data_type"],
        control_type=request.form["control_type"],
        options=request.form.get("options", ""),
        required=bool(request.form.get("required")),
    )
    db.session.add(field)
    db.session.commit()
    flash("Campo agregado", "success")
    return redirect(url_for("admin_panel"))


@app.route("/admin/ticket-classes/<int:class_id>/template", methods=["POST"])
def upload_template(class_id: int):
    upload = save_upload(request.files.get("template_attachment"))
    if upload:
        db.session.add(TicketTemplateAttachment(ticket_class_id=class_id, original_filename=upload[0], stored_filename=upload[1]))
        db.session.commit()
        flash("Adjunto de clase cargado", "success")
    return redirect(url_for("admin_panel"))


@app.route("/files/<stored_filename>")
def download_file(stored_filename: str):
    return send_from_directory(UPLOAD_DIR, stored_filename, as_attachment=True)


@app.cli.command("init-db")
def init_db():
    db.create_all()
    print("Base de datos inicializada")


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True, host="0.0.0.0", port=5000)
