from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager
from models import db, User
import re

login_manager = LoginManager()


@login_manager.user_loader
def load_user(user_id):
    """Flask-Login用户加载回调"""
    return User.query.get(int(user_id))


def validate_username(username):
    """验证用户名格式"""
    if not username or len(username) < 3 or len(username) > 80:
        return False, "用户名长度必须在3-80个字符之间"
    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        return False, "用户名只能包含字母、数字和下划线"
    return True, ""


def validate_email(email):
    """验证邮箱格式"""
    if not email:
        return False, "邮箱不能为空"
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        return False, "邮箱格式不正确"
    return True, ""


def validate_password(password):
    """验证密码强度"""
    if not password or len(password) < 6:
        return False, "密码长度至少为6个字符"
    if len(password) > 128:
        return False, "密码长度不能超过128个字符"
    # 检查是否包含至少一个字母和一个数字
    if not re.search(r'[a-zA-Z]', password) or not re.search(r'[0-9]', password):
        return False, "密码必须包含至少一个字母和一个数字"
    return True, ""


def register_user(username, email, password, role='operator'):
    """注册新用户"""
    # 验证用户名
    valid, msg = validate_username(username)
    if not valid:
        return False, msg

    # 验证邮箱
    valid, msg = validate_email(email)
    if not valid:
        return False, msg

    # 验证密码
    valid, msg = validate_password(password)
    if not valid:
        return False, msg

    # 检查用户名是否已存在
    if User.query.filter_by(username=username).first():
        return False, "用户名已被使用"

    # 检查邮箱是否已存在
    if User.query.filter_by(email=email).first():
        return False, "邮箱已被注册"

    # 创建新用户
    try:
        password_hash = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(
            username=username,
            email=email,
            password_hash=password_hash,
            role=role
        )
        db.session.add(new_user)
        db.session.commit()
        return True, "注册成功"
    except Exception as e:
        db.session.rollback()
        return False, f"注册失败: {str(e)}"


def authenticate_user(username, password):
    """验证用户登录"""
    if not username or not password:
        return None, "用户名和密码不能为空"

    user = User.query.filter_by(username=username).first()
    if not user:
        return None, "用户名或密码错误"

    if not check_password_hash(user.password_hash, password):
        return None, "用户名或密码错误"

    return user, "登录成功"


def change_password(user, old_password, new_password):
    """修改密码"""
    if not check_password_hash(user.password_hash, old_password):
        return False, "原密码错误"

    # 验证新密码
    valid, msg = validate_password(new_password)
    if not valid:
        return False, msg

    try:
        user.password_hash = generate_password_hash(new_password, method='pbkdf2:sha256')
        db.session.commit()
        return True, "密码修改成功"
    except Exception as e:
        db.session.rollback()
        return False, f"密码修改失败: {str(e)}"


def is_admin(user):
    """检查用户是否是管理员"""
    return user and user.role == 'admin'
