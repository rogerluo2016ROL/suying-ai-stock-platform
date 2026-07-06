package com.ds.cockpit.screen.system.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.ds.cockpit.screen.common.core.domain.entity.SystemUserNoviceGuideEntity;
import com.ds.cockpit.screen.common.core.domain.entity.vo.SystemUserNoviceGuideVo;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** 开发环境使用
* @author zhouhong
* @description 针对表【system_user_novice_guide】的数据库操作Mapper
* @createDate 2024-02-01
*/
@Mapper
public interface SystemUserNoviceGuideMapper extends BaseMapper<SystemUserNoviceGuideEntity> {

    SystemUserNoviceGuideEntity getSystemUserNoviceGuide(@Param("vo") SystemUserNoviceGuideVo vo);

    int insertEntity(SystemUserNoviceGuideEntity userNoviceGuideEntity);

    int unAvailability(Long id);
}




