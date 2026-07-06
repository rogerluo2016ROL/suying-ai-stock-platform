package com.ds.cockpit.screen.system.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.ds.cockpit.screen.common.core.domain.entity.SystemUserDefinedMenuEntity;
import com.ds.cockpit.screen.common.core.domain.entity.vo.DmUserMenuRequestVo;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;

/**
* @author 18771
* @description 针对表【system_user_defined_menu】的数据库操作Mapper
* @createDate 2023-12-15 14:47:28
* @Entity generator.domain.SystemUserDefinedMenu
*/
@Mapper
public interface SystemUserDefinedMenuMapper extends BaseMapper<SystemUserDefinedMenuEntity> {

    boolean deleteBatchByMenuCode(@Param("vo")DmUserMenuRequestVo vo);

    List<SystemUserDefinedMenuEntity> selectDefinedMenuByUserId(@Param("userId") String userId);

    List<SystemUserDefinedMenuEntity> selectAllMenuByUserId(@Param("userId") String userId);

    void deleteBatchUserIds(@Param("entities") List<SystemUserDefinedMenuEntity> collect);

    void insertBatch(@Param("entities") List<SystemUserDefinedMenuEntity> collect);

    List<SystemUserDefinedMenuEntity> selectByUserId(@Param("userId") String userId);

    Long selectCountByUserId(@Param("userId") String userId);

    List<SystemUserDefinedMenuEntity> selectLikeByName(@Param("userId") String userId , @Param("name") String name);

    boolean deleteBatchByUserId(@Param("userId") String userId);

    List<SystemUserDefinedMenuEntity> selectByParentIdAndUserId(@Param("parentId") Integer parentId, @Param("userId") String userId);

    int updateEntity(SystemUserDefinedMenuEntity systemUserDefinedMenuEntity);

}




