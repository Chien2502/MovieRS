"""Test mặc định chỉ dùng file tạm; không được tự chọn database trong .env thật."""

import os

os.environ['MOVIERS_STORAGE']='files'
os.environ['AUTO_RETRAIN']='0'
os.environ['MOVIERS_SERVING_POINTER']=''
os.environ['DATABASE_POOL_SIZE']='0'
