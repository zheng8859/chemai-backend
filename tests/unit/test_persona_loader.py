"""Persona 配置加载器测试。

覆盖：
- 四个 Persona YAML 加载成功
- 必填字段缺失报错
- available_skills 非空验证
"""

import tempfile
from pathlib import Path

import pytest
import yaml

from app.agent.persona.loader import (
    PersonaConfig,
    load_persona,
    load_all_personas,
    get_available_persona_names,
    _validate_config,
)


class TestPersonaLoading:
    """测试从 YAML 文件加载 Persona 配置。"""

    def test_load_teacher_persona(self):
        """教师 Persona 加载成功。"""
        config = load_persona("teacher")
        assert config.name == "teacher"
        assert config.display_name == "教师助手"
        assert len(config.available_skills) > 0
        assert "search_exam_bank" in config.available_skills
        assert "diagnose_barrier" in config.available_skills
        assert isinstance(config.system_prompt, str)
        assert len(config.system_prompt) > 50

    def test_load_student_persona(self):
        """学生 Persona 加载成功。"""
        config = load_persona("student")
        assert config.name == "student"
        assert config.display_name == "学生助手"
        assert len(config.available_skills) > 0
        # 6 个 Socratic 辅导工具
        assert "ionic_equation_tutor" in config.available_skills
        assert "equilibrium_tutor" in config.available_skills
        assert "chemistry_tutor" in config.available_skills
        assert "memory_student_get" in config.available_skills

    def test_load_tutor_persona(self):
        """助教 Persona 加载成功。"""
        config = load_persona("tutor")
        assert config.name == "tutor"
        assert config.display_name == "助教助手"
        assert len(config.available_skills) > 0
        assert "chemistry_tutor" in config.available_skills

    def test_load_parent_persona(self):
        """家长 Persona 加载成功。"""
        config = load_persona("parent")
        assert config.name == "parent"
        assert config.display_name == "家长助手"
        assert len(config.available_skills) > 0
        assert "weekly_report" in config.available_skills
        assert "diagnose_barrier" in config.available_skills
        assert config.data_access is not None
        assert config.data_access["scope"] == "child_only"

    def test_load_nonexistent_persona_raises(self):
        """不存在的 Persona 抛出 FileNotFoundError。"""
        with pytest.raises(FileNotFoundError):
            load_persona("nonexistent_role")

    def test_load_all_personas(self):
        """load_all_personas 返回所有 Persona。"""
        all_configs = load_all_personas()
        assert len(all_configs) >= 4
        assert "teacher" in all_configs
        assert "student" in all_configs
        assert "tutor" in all_configs
        assert "parent" in all_configs
        # 所有 config 都是 PersonaConfig 实例
        for cfg in all_configs.values():
            assert isinstance(cfg, PersonaConfig)
            assert len(cfg.available_skills) > 0

    def test_get_available_persona_names(self):
        """get_available_persona_names 返回角色名列表。"""
        names = get_available_persona_names()
        assert "teacher" in names
        assert "student" in names
        assert "tutor" in names
        assert "parent" in names


class TestPersonaValidation:
    """测试 Persona 配置验证逻辑。"""

    @staticmethod
    def _write_temp_yaml(data: dict) -> Path:
        """将字典写入临时 YAML 文件，返回路径。"""
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        )
        yaml.dump(data, tmp, allow_unicode=True)
        tmp.close()
        return Path(tmp.name)

    def test_valid_config_passes(self):
        """完整配置通过验证。"""
        data = {
            "persona": {
                "name": "test",
                "display_name": "测试",
                "description": "测试角色",
            },
            "system_prompt": "你是一个测试助手。",
            "available_skills": ["skill_a", "skill_b"],
        }
        path = self._write_temp_yaml(data)
        try:
            _validate_config(data, path)  # 不应抛异常
        finally:
            path.unlink()

    def test_missing_system_prompt_raises(self):
        """缺少 system_prompt 抛出 ValueError。"""
        data = {
            "persona": {
                "name": "test",
                "display_name": "测试",
                "description": "测试角色",
            },
            "available_skills": ["skill_a"],
        }
        path = self._write_temp_yaml(data)
        try:
            with pytest.raises(ValueError, match="system_prompt"):
                _validate_config(data, path)
        finally:
            path.unlink()

    def test_empty_skills_raises(self):
        """available_skills 为空列表抛出 ValueError。"""
        data = {
            "persona": {
                "name": "test",
                "display_name": "测试",
                "description": "测试角色",
            },
            "system_prompt": "你是一个测试助手。",
            "available_skills": [],
        }
        path = self._write_temp_yaml(data)
        try:
            with pytest.raises(ValueError, match="非空列表"):
                _validate_config(data, path)
        finally:
            path.unlink()

    def test_missing_persona_name_raises(self):
        """缺少 persona.name 抛出 ValueError。"""
        data = {
            "persona": {
                "display_name": "测试",
                "description": "测试角色",
            },
            "system_prompt": "你是一个测试助手。",
            "available_skills": ["skill_a"],
        }
        path = self._write_temp_yaml(data)
        try:
            with pytest.raises(ValueError, match="name"):
                _validate_config(data, path)
        finally:
            path.unlink()

    def test_non_list_skills_raises(self):
        """available_skills 不是列表抛出 ValueError。"""
        data = {
            "persona": {
                "name": "test",
                "display_name": "测试",
                "description": "测试角色",
            },
            "system_prompt": "你是一个测试助手。",
            "available_skills": "skill_a",  # 字符串而非列表
        }
        path = self._write_temp_yaml(data)
        try:
            with pytest.raises(ValueError, match="非空列表"):
                _validate_config(data, path)
        finally:
            path.unlink()
