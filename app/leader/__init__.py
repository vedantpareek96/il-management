from flask import Blueprint

bp = Blueprint('leader', __name__)

from . import routes
