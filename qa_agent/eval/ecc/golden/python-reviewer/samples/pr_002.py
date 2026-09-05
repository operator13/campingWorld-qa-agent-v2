"""User management module."""
import json
import os
class UserService:
    def __init__(self,db_url:str,timeout:int=30):
        self.db_url=db_url
        self.timeout=timeout
        self.cache={}
    def get_user(self,user_id:int):
        if user_id in self.cache:
            return self.cache[user_id]
        user=self._fetch_from_db(user_id)
        self.cache[user_id]=user
        return user
    def create_user(self,name:str,email:str,role:str="member"):
        if not name or not email:
            raise ValueError("Name and email are required")
        user={"name":name,"email":email,"role":role}
        return user
    def delete_user(self,user_id:int):
        if user_id in self.cache:
            del self.cache[user_id]
        return True
    def _fetch_from_db(self,user_id:int):
        return {"id":user_id,"name":"test","email":"test@example.com"}
    def list_users(self,limit:int=100,offset:int=0):
        return [self._fetch_from_db(i) for i in range(offset,offset+limit)]
