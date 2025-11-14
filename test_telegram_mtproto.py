#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram MTPROTO 测试脚本
用于测试能否正常获取群组消息
"""

import asyncio
import sys
from telethon import TelegramClient, events
from telethon.tl.types import User, Chat, Channel
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError
from telethon.sessions import StringSession

# 配置信息
API_ID = 37878745
API_HASH = '1b87612d3752d55fc17384d2d4932f19'

# 会话文件名（用于保存登录状态）
SESSION_FILE = 'telegram_test.session'

class TelegramMTProtoTester:
    """Telegram MTPROTO 测试类"""
    
    def __init__(self, api_id, api_hash, session_file):
        """
        初始化客户端
        
        Args:
            api_id: Telegram API ID
            api_hash: Telegram API Hash
            session_file: 会话文件名
        """
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_file = session_file
        self.client = None
        self.is_authenticated = False
    
    async def initialize(self):
        """初始化客户端连接"""
        try:
            print(f"🔌 正在连接 Telegram...")
            print(f"   API ID: {self.api_id}")
            print(f"   API Hash: {self.api_hash[:10]}...")
            
            # 创建客户端
            self.client = TelegramClient(
                self.session_file,
                self.api_id,
                self.api_hash
            )
            
            # 连接
            await self.client.connect()
            print("✅ 连接成功")
            
            # 检查是否已认证
            if await self.client.is_user_authorized():
                self.is_authenticated = True
                me = await self.client.get_me()
                print(f"✅ 已认证用户: {me.first_name} (@{me.username or 'N/A'})")
                return True
            else:
                print("⚠️  未认证，需要登录")
                return False
                
        except Exception as e:
            print(f"❌ 初始化失败: {e}")
            return False
    
    async def login(self, phone=None):
        """
        登录 Telegram 账户
        
        Args:
            phone: 手机号码（格式: +8613800138000）
        """
        if not self.client:
            print("❌ 客户端未初始化")
            return False
        
        try:
            if self.is_authenticated:
                print("✅ 已经登录")
                return True
            
            # 如果没有提供手机号，提示输入
            if not phone:
                phone = input("\n📱 请输入手机号码 (格式: +8613800138000): ").strip()
            
            if not phone:
                print("❌ 手机号码不能为空")
                return False
            
            print(f"\n📤 正在发送验证码到 {phone}...")
            
            # 发送验证码
            await self.client.send_code_request(phone)
            print("✅ 验证码已发送，请查看 Telegram 应用")
            
            # 输入验证码
            code = input("📝 请输入收到的验证码: ").strip()
            if not code:
                print("❌ 验证码不能为空")
                return False
            
            try:
                # 使用验证码登录
                await self.client.sign_in(phone, code)
                self.is_authenticated = True
                
                me = await self.client.get_me()
                print(f"✅ 登录成功: {me.first_name} (@{me.username or 'N/A'})")
                return True
                
            except SessionPasswordNeededError:
                # 需要两步验证密码
                print("🔐 需要两步验证密码")
                password = input("请输入两步验证密码: ").strip()
                
                if not password:
                    print("❌ 密码不能为空")
                    return False
                
                await self.client.sign_in(password=password)
                self.is_authenticated = True
                
                me = await self.client.get_me()
                print(f"✅ 两步验证成功: {me.first_name} (@{me.username or 'N/A'})")
                return True
                
            except PhoneCodeInvalidError:
                print("❌ 验证码无效")
                return False
                
        except Exception as e:
            print(f"❌ 登录失败: {e}")
            return False
    
    async def get_dialogs(self):
        """获取所有对话列表（包括群组）"""
        if not self.client or not self.is_authenticated:
            print("❌ 客户端未认证")
            return []
        
        try:
            print("\n📋 正在获取对话列表...")
            dialogs = []
            
            async for dialog in self.client.iter_dialogs():
                entity = dialog.entity
                dialog_info = {
                    'id': dialog.id,
                    'title': dialog.title,
                    'unread_count': dialog.unread_count,
                    'type': None,
                    'username': None,
                    'is_group': False,
                    'is_channel': False,
                    'is_private': False
                }
                
                # 判断类型
                if isinstance(entity, User):
                    dialog_info['type'] = 'private'
                    dialog_info['is_private'] = True
                    dialog_info['username'] = entity.username
                elif isinstance(entity, Chat):
                    dialog_info['type'] = 'group'
                    dialog_info['is_group'] = True
                elif isinstance(entity, Channel):
                    dialog_info['type'] = 'channel'
                    dialog_info['is_channel'] = True
                    dialog_info['username'] = entity.username
                
                dialogs.append(dialog_info)
            
            print(f"✅ 获取到 {len(dialogs)} 个对话")
            return dialogs
            
        except Exception as e:
            print(f"❌ 获取对话列表失败: {e}")
            return []
    
    async def get_group_messages(self, chat_id=None, limit=10):
        """
        获取群组消息
        
        Args:
            chat_id: 群组ID或用户名（如果为None，则列出所有群组让用户选择）
            limit: 获取消息数量
        """
        if not self.client or not self.is_authenticated:
            print("❌ 客户端未认证")
            return []
        
        try:
            # 如果没有指定chat_id，先列出群组
            if chat_id is None:
                dialogs = await self.get_dialogs()
                
                # 筛选出群组和频道
                groups = [d for d in dialogs if d['is_group'] or d['is_channel']]
                
                if not groups:
                    print("❌ 未找到任何群组或频道")
                    return []
                
                print("\n📋 找到以下群组/频道:")
                print("-" * 60)
                for i, group in enumerate(groups, 1):
                    group_type = "频道" if group['is_channel'] else "群组"
                    username_text = f"(@{group['username']})" if group['username'] else ""
                    print(f"{i}. {group['title']} {username_text} [{group_type}]")
                    print(f"   ID: {group['id']}")
                
                # 让用户选择
                try:
                    choice = int(input(f"\n请选择要查看消息的群组/频道 (1-{len(groups)}): ").strip()) - 1
                    if 0 <= choice < len(groups):
                        chat_id = groups[choice]['id']
                        chat_title = groups[choice]['title']
                    else:
                        print("❌ 无效选择")
                        return []
                except ValueError:
                    print("❌ 请输入有效数字")
                    return []
            else:
                chat_title = str(chat_id)
            
            print(f"\n📨 正在获取 '{chat_title}' 的最新 {limit} 条消息...")
            
            messages = []
            async for message in self.client.iter_messages(chat_id, limit=limit):
                sender = await message.get_sender()
                sender_name = sender.first_name if sender else "未知"
                sender_username = getattr(sender, 'username', None) if sender else None
                
                message_info = {
                    'id': message.id,
                    'date': message.date,
                    'text': message.text or '[媒体/文件]',
                    'sender_id': message.sender_id,
                    'sender_name': sender_name,
                    'sender_username': sender_username,
                    'is_reply': message.is_reply,
                    'reply_to_msg_id': message.reply_to_msg_id if message.is_reply else None
                }
                messages.append(message_info)
            
            print(f"✅ 获取到 {len(messages)} 条消息")
            return messages
            
        except Exception as e:
            print(f"❌ 获取消息失败: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    async def listen_group_messages(self, chat_ids=None, duration=None, continuous=False):
        """
        监听群组消息（支持多群组）
        
        Args:
            chat_ids: 群组ID列表（如果为None，则监听所有群组）
            duration: 监听时长（秒），如果为None且continuous=False，则持续60秒
            continuous: 是否持续运行（24小时不间断）
        """
        if not self.client or not self.is_authenticated:
            print("❌ 客户端未认证")
            return
        
        try:
            # 如果没有指定群组，让用户选择
            if chat_ids is None:
                dialogs = await self.get_dialogs()
                groups = [d for d in dialogs if d['is_group'] or d['is_channel']]
                
                if not groups:
                    print("❌ 未找到任何群组或频道")
                    return
                
                print("\n📋 选择要监听的群组/频道（可多选）:")
                print("-" * 60)
                for i, group in enumerate(groups, 1):
                    group_type = "频道" if group['is_channel'] else "群组"
                    username_text = f"(@{group['username']})" if group['username'] else ""
                    print(f"{i}. {group['title']} {username_text} [{group_type}]")
                    print(f"   ID: {group['id']}")
                
                print(f"{len(groups) + 1}. 监听所有群组/频道")
                print(f"{len(groups) + 2}. 取消")
                
                try:
                    choice_input = input(f"\n请选择要监听的群组 (多个用逗号分隔, 1-{len(groups) + 2}): ").strip()
                    
                    if choice_input == str(len(groups) + 2):
                        print("❌ 已取消")
                        return
                    
                    if choice_input == str(len(groups) + 1):
                        # 监听所有群组
                        chat_ids = [g['id'] for g in groups]
                        print(f"✅ 将监听所有 {len(chat_ids)} 个群组/频道")
                    else:
                        # 选择特定群组
                        choices = [int(x.strip()) - 1 for x in choice_input.split(',')]
                        chat_ids = [groups[i]['id'] for i in choices if 0 <= i < len(groups)]
                        
                        if not chat_ids:
                            print("❌ 无效选择")
                            return
                        
                        selected_titles = [groups[i]['title'] for i in choices if 0 <= i < len(groups)]
                        print(f"✅ 将监听以下 {len(chat_ids)} 个群组/频道:")
                        for title in selected_titles:
                            print(f"   - {title}")
                except ValueError:
                    print("❌ 输入格式错误")
                    return
            
            # 确定监听时长
            if continuous:
                duration_text = "24小时不间断"
                duration = None  # 持续运行
            elif duration is None:
                duration = 60
                duration_text = f"{duration} 秒"
            else:
                duration_text = f"{duration} 秒"
            
            print(f"\n👂 开始监听群组消息 ({duration_text})...")
            print("按 Ctrl+C 可提前停止")
            print("-" * 60)
            
            message_count = 0
            start_time = asyncio.get_event_loop().time()
            
            # 创建群组ID集合用于快速查找
            target_chat_ids = set(chat_ids) if chat_ids else None
            
            @self.client.on(events.NewMessage)
            async def handle_new_message(event):
                nonlocal message_count
                
                # 如果指定了群组列表，只处理这些群组的消息
                if target_chat_ids is not None and event.chat_id not in target_chat_ids:
                    return
                
                message_count += 1
                
                # 获取发送者信息
                sender = await event.get_sender()
                sender_name = sender.first_name if sender else "未知"
                sender_username = getattr(sender, 'username', None) if sender else None
                
                # 获取聊天信息
                chat = await event.get_chat()
                chat_title = getattr(chat, 'title', None) or str(chat.id)
                
                # 格式化时间
                msg_time = event.message.date.strftime("%Y-%m-%d %H:%M:%S")
                
                print(f"\n📨 [{message_count}] {msg_time}")
                print(f"   群组: {chat_title}")
                print(f"   发送者: {sender_name} (@{sender_username or 'N/A'})")
                print(f"   内容: {event.message.text or '[媒体/文件]'}")
                print("-" * 60)
            
            # 持续运行
            if continuous or duration is None:
                print("🔄 持续监听中... (按 Ctrl+C 停止)")
                
                # 启动统计任务（每小时输出一次）
                async def stats_task():
                    while True:
                        await asyncio.sleep(3600)  # 每小时
                        elapsed = asyncio.get_event_loop().time() - start_time
                        hours = int(elapsed // 3600)
                        minutes = int((elapsed % 3600) // 60)
                        print(f"\n⏱️  已运行 {hours}小时{minutes}分钟，共收到 {message_count} 条消息")
                        print("-" * 60)
                
                # 启动统计任务
                stats_task_obj = asyncio.create_task(stats_task())
                
                try:
                    # 持续运行，直到用户中断或连接断开
                    await self.client.run_until_disconnected()
                except KeyboardInterrupt:
                    stats_task_obj.cancel()
                    elapsed = asyncio.get_event_loop().time() - start_time
                    hours = int(elapsed // 3600)
                    minutes = int((elapsed % 3600) // 60)
                    print(f"\n\n👋 用户中断，监听结束")
                    print(f"⏱️  总运行时间: {hours}小时{minutes}分钟")
                    print(f"📨 共收到 {message_count} 条消息")
                except Exception as e:
                    stats_task_obj.cancel()
                    print(f"\n❌ 连接断开: {e}")
                    elapsed = asyncio.get_event_loop().time() - start_time
                    hours = int(elapsed // 3600)
                    minutes = int((elapsed % 3600) // 60)
                    print(f"⏱️  总运行时间: {hours}小时{minutes}分钟")
                    print(f"📨 共收到 {message_count} 条消息")
            else:
                # 运行指定时长
                await asyncio.sleep(duration)
                elapsed = asyncio.get_event_loop().time() - start_time
                print(f"\n✅ 监听结束")
                print(f"⏱️  运行时间: {int(elapsed)}秒")
                print(f"📨 共收到 {message_count} 条消息")
            
        except KeyboardInterrupt:
            elapsed = asyncio.get_event_loop().time() - start_time
            hours = int(elapsed // 3600)
            minutes = int((elapsed % 3600) // 60)
            print(f"\n\n👋 用户中断，监听结束")
            print(f"⏱️  总运行时间: {hours}小时{minutes}分钟")
            print(f"📨 共收到 {message_count} 条消息")
        except Exception as e:
            print(f"❌ 监听失败: {e}")
            import traceback
            traceback.print_exc()
    
    async def print_messages(self, messages):
        """打印消息列表"""
        if not messages:
            print("📭 没有消息")
            return
        
        print("\n" + "=" * 60)
        print("📨 消息列表")
        print("=" * 60)
        
        for i, msg in enumerate(messages, 1):
            sender_text = f"{msg['sender_name']}"
            if msg['sender_username']:
                sender_text += f" (@{msg['sender_username']})"
            
            print(f"\n[{i}] {msg['date']}")
            print(f"    发送者: {sender_text}")
            print(f"    内容: {msg['text']}")
            if msg['is_reply']:
                print(f"    [回复消息 ID: {msg['reply_to_msg_id']}]")
    
    async def disconnect(self):
        """断开连接"""
        if self.client:
            await self.client.disconnect()
            print("✅ 已断开连接")

async def main():
    """主函数"""
    print("=" * 60)
    print("🚀 Telegram MTPROTO 测试工具")
    print("=" * 60)
    
    # 创建测试实例
    tester = TelegramMTProtoTester(API_ID, API_HASH, SESSION_FILE)
    
    try:
        # 初始化
        if not await tester.initialize():
            # 需要登录
            if not await tester.login():
                print("❌ 登录失败，退出")
                return
        
        # 主菜单循环
        while True:
            print("\n" + "=" * 60)
            print("📋 主菜单")
            print("=" * 60)
            print("1. 📋 获取对话列表（包括群组）")
            print("2. 📨 获取群组消息")
            print("3. 👂 监听群组消息（60秒）")
            print("4. 🔄 监听群组消息（24小时不间断）")
            print("5. 🔄 重新登录")
            print("6. ❌ 退出")
            print("-" * 60)
            
            choice = input("请选择操作 (1-6): ").strip()
            
            if choice == '1':
                dialogs = await tester.get_dialogs()
                if dialogs:
                    print("\n📋 对话列表:")
                    print("-" * 60)
                    for i, dialog in enumerate(dialogs, 1):
                        type_text = {
                            'private': '私聊',
                            'group': '群组',
                            'channel': '频道'
                        }.get(dialog['type'], '未知')
                        
                        username_text = f"(@{dialog['username']})" if dialog['username'] else ""
                        unread_text = f" [{dialog['unread_count']}条未读]" if dialog['unread_count'] > 0 else ""
                        
                        print(f"{i}. {dialog['title']} {username_text} [{type_text}]{unread_text}")
                        print(f"   ID: {dialog['id']}")
            
            elif choice == '2':
                messages = await tester.get_group_messages()
                if messages:
                    await tester.print_messages(messages)
            
            elif choice == '3':
                await tester.listen_group_messages(duration=60)
            
            elif choice == '4':
                print("\n⚠️  24小时不间断监听模式")
                print("提示：")
                print("  - 可以监听多个群组")
                print("  - 程序将持续运行直到手动停止")
                print("  - 按 Ctrl+C 可随时停止")
                confirm = input("\n确认开始24小时监听？(y/N): ").strip().lower()
                if confirm == 'y':
                    await tester.listen_group_messages(continuous=True)
                else:
                    print("❌ 已取消")
            
            elif choice == '5':
                await tester.disconnect()
                tester.is_authenticated = False
                if not await tester.initialize():
                    await tester.login()
            
            elif choice == '6':
                print("👋 退出测试工具")
                break
            
            else:
                print("❌ 无效选择，请输入 1-6")
    
    except KeyboardInterrupt:
        print("\n\n👋 用户中断，退出")
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await tester.disconnect()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 程序已退出")

