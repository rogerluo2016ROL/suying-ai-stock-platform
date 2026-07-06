package com.ds.cockpit.screen.system.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.ds.cockpit.screen.common.core.domain.entity.SystemMessageEntity;
import com.ds.cockpit.screen.common.core.domain.entity.vo.SystemMessageVo;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;


/**
* @author 18771
* @description 针对表【system_notice(系统公告表)】的数据库操作Mapper
* @createDate 2023-08-17 12:15:11
* @Entity generator.domain.SystemNotice
*/
@Mapper
public interface SystemMessageMapper extends BaseMapper<SystemMessageEntity> {

    List<SystemMessageEntity> getMessages(@Param("vo") SystemMessageVo vo);

    int insertEntity(SystemMessageEntity systemMessageEntity);

    SystemMessageEntity selectByEntityId(Long id);

    int unAvailability(Long id);

    int unSendUrgentNotice(Long id);

    int sendUrgentNotice(Long id);

    int updateEntity(SystemMessageEntity systemMessageEntity);
}




