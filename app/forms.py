from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, DateField, IntegerField, TextAreaField, SelectField, SelectMultipleField
from wtforms.validators import DataRequired, Length, NumberRange, Optional, ValidationError
from wtforms.widgets import TextArea
from datetime import date

from app.models import Person, RoleEnum


class SignupForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=80)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    name = StringField('Name', validators=[DataRequired(), Length(max=200)])
    region = StringField('Region', validators=[DataRequired(), Length(max=100)])
    role = SelectField(
        'Role',
        choices=[(r.value, r.name.title()) for r in RoleEnum if r != RoleEnum.ADMIN],
        default=RoleEnum.LEADER.value,
        validators=[DataRequired()]
    )


class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])


class RegisterStatisticForm(FlaskForm):
    date = DateField('Date', validators=[DataRequired()], default=date.today)
    location = StringField('Location', validators=[DataRequired()])
    participants = SelectMultipleField('Participants', coerce=str, validators=[DataRequired()])
    room_captain_id = SelectField('Room Captain', coerce=str, validators=[Optional()])
    guests_count = IntegerField('Guests Count', validators=[DataRequired(), NumberRange(min=0)])
    registrations_count = IntegerField('Registrations Count', validators=[DataRequired(), NumberRange(min=0)])
    notes = TextAreaField('Notes', validators=[Optional()], widget=TextArea())
    
    def validate_registrations_count(self, field):
        if self.guests_count.data is not None and field.data is not None:
            if field.data > self.guests_count.data:
                raise ValidationError('Registrations count cannot exceed guests count')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.room_captain_id.choices = [("", "— None —")] + [
            (str(person.id), person.name)
            for person in Person.query
            .filter(Person.role == RoleEnum.LEADER)
            .order_by(Person.name)
            .all()
        ]

class StaffStatsFilterForm(FlaskForm):
    region = SelectField('Region', coerce=str, validators=[Optional()])
    date_from = DateField('Date From', validators=[Optional()])
    date_to = DateField('Date To', validators=[Optional()])


class LeaderboardFilterForm(FlaskForm):
    region = SelectField('Region', coerce=str, validators=[Optional()])
    date_from = DateField('Date From', validators=[Optional()])
    date_to = DateField('Date To', validators=[Optional()])
    metric = SelectField('Sort By', choices=[
        ('registrations', 'Registrations'),
        ('guests', 'Guests'),
        ('effectiveness', 'Effectiveness')
    ], default='registrations', validators=[Optional()])


class CriteriaForm(FlaskForm):
    person_id = SelectField('Person (leave empty for global)', coerce=str, validators=[Optional()])
    guests_target = IntegerField('Guests Target', validators=[Optional(), NumberRange(min=0)])
    registrations_target = IntegerField('Registrations Target', validators=[Optional(), NumberRange(min=0)])
    effectiveness_target_pct = IntegerField('Effectiveness Target %', validators=[Optional(), NumberRange(min=0, max=100)])
